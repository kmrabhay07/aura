"""Keep only Jarvis-launched browser children inside an app-owned Windows job."""
import sys
import threading


class BrowserProcessGuard:
    def __init__(self):
        self.handle=None
        self._lock=threading.Lock()
        self._closed=False

    def attach(self,pid):
        if sys.platform!='win32':
            return
        import ctypes as c
        from ctypes import wintypes as w
        class Basic(c.Structure):
            _fields_=[('PerProcessUserTimeLimit',c.c_int64),('PerJobUserTimeLimit',c.c_int64),
                ('LimitFlags',w.DWORD),('MinimumWorkingSetSize',c.c_size_t),('MaximumWorkingSetSize',c.c_size_t),
                ('ActiveProcessLimit',w.DWORD),('Affinity',c.c_size_t),('PriorityClass',w.DWORD),('SchedulingClass',w.DWORD)]
        class Counters(c.Structure):
            _fields_=[(name,c.c_uint64) for name in ('ReadOperationCount','WriteOperationCount','OtherOperationCount',
                                                 'ReadTransferCount','WriteTransferCount','OtherTransferCount')]
        class Limits(c.Structure):
            _fields_=[('BasicLimitInformation',Basic),('IoInfo',Counters),('ProcessMemoryLimit',c.c_size_t),
                ('JobMemoryLimit',c.c_size_t),('PeakProcessMemoryUsed',c.c_size_t),('PeakJobMemoryUsed',c.c_size_t)]
        api=c.WinDLL('kernel32',use_last_error=True)
        api.CreateJobObjectW.argtypes=(c.c_void_p,w.LPCWSTR)
        api.CreateJobObjectW.restype=w.HANDLE
        api.SetInformationJobObject.argtypes=(w.HANDLE,c.c_int,c.c_void_p,w.DWORD)
        api.SetInformationJobObject.restype=w.BOOL
        api.OpenProcess.argtypes=(w.DWORD,w.BOOL,w.DWORD)
        api.OpenProcess.restype=w.HANDLE
        api.AssignProcessToJobObject.argtypes=(w.HANDLE,w.HANDLE)
        api.AssignProcessToJobObject.restype=w.BOOL
        api.CloseHandle.argtypes=(w.HANDLE,)
        api.CloseHandle.restype=w.BOOL
        with self._lock:
            if self._closed:
                raise RuntimeError('Browser is closing')
            job=api.CreateJobObjectW(None,None)
            if not job:
                raise OSError('Could not create browser process guard')
            process=None
            try:
                limits=Limits()
                limits.BasicLimitInformation.LimitFlags=0x2000  # KILL_ON_JOB_CLOSE
                if not api.SetInformationJobObject(job,9,c.byref(limits),c.sizeof(limits)):
                    raise OSError('Could not configure browser process guard')
                process=api.OpenProcess(0x0100|0x0001,False,int(pid))
                if not process or not api.AssignProcessToJobObject(job,process):
                    raise OSError('Could not isolate browser child process')
                if self.handle:
                    api.CloseHandle(self.handle)
                self.handle=job
                job=None
            finally:
                if process: api.CloseHandle(process)
                if job: api.CloseHandle(job)

    def close(self,permanent=False):
        with self._lock:
            if permanent:
                self._closed=True
            if self.handle and sys.platform=='win32':
                import ctypes as c
                from ctypes import wintypes as w
                api=c.WinDLL('kernel32',use_last_error=True)
                api.CloseHandle.argtypes=(w.HANDLE,)
                api.CloseHandle.restype=w.BOOL
                api.CloseHandle(self.handle)
                self.handle=None
