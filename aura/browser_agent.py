"""A separately approved browser session, isolated from existing user profiles."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import queue
import re
import threading
from urllib.parse import urlparse
from .process_guard import BrowserProcessGuard

BROWSER_TOOL = {'type':'function','function':{
    'name':'jarvis_browser','description':'Use the separate Jarvis browser. Open a URL, read the current page, click or fill a target from the latest read, or go back. Each step requires user approval. No passwords, codes, payments or file uploads.',
    'parameters':{'type':'object','properties':{
        'action':{'type':'string','enum':['open','read','click','fill','back']},
        'url':{'type':'string'},'target':{'type':'string'},'text':{'type':'string'}},
        'required':['action'],'additionalProperties':False}}}


def validate_url(value):
    parsed=urlparse(value)
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Only ordinary http/https URLs may be opened')
    return value


def site_label(url):
    p=urlparse(url)
    return p.scheme+'://'+p.netloc+p.path


def sensitive_field(description):
    return bool(re.search(r'password|one.?time|verification|security.?code|credit|card.?number|cvv|cvc|api.?key|auth.?token|secret|social.?security',description,re.I))


@dataclass
class BrowserRequest:
    action: str
    args: dict
    turn: object
    expected: object = None
    event: threading.Event = field(default_factory=threading.Event)
    result: object = None
    failed: bool = False


class BrowserAgent:
    def __init__(self, profile_path=None, factory=None):
        self.profile_path=Path(profile_path or Path(os.getenv('LOCALAPPDATA',str(Path.home()))) / 'Jarvis' / 'BrowserProfile')
        self.factory=factory
        self.commands=queue.Queue(maxsize=16)
        self.closed=threading.Event()
        self._thread=None
        self._start_lock=threading.Lock()
        self.guard=BrowserProcessGuard()

    def request(self, action, args, turn, expected=None):
        turn.check()
        if self.closed.is_set():
            raise RuntimeError('Jarvis browser is closed')
        with self._start_lock:
            if self._thread is None:
                self._thread=threading.Thread(target=self._run,daemon=True,name='Jarvis browser')
                self._thread.start()
        request=BrowserRequest(action,dict(args),turn,expected)
        self.commands.put(request,timeout=1)
        while not request.event.wait(.05):
            turn.check()
            if self.closed.is_set():
                raise RuntimeError('Jarvis browser is closed')
        turn.check()
        if request.failed:
            raise RuntimeError('Browser setup or action failed. Check installed Edge and the browser runtime, then open/read the page again. Protected fields and non-web pages are blocked.')
        return request.result

    def review(self,args,turn):
        return self.request('review',args,turn)

    def perform(self,args,turn,expected):
        return self.request('perform',args,turn,expected)

    def close(self):
        self.closed.set()
        self.guard.close(permanent=True)

    def _run(self):
        runtime=None
        context=None
        page=None
        targets={}
        snapshot_url=''
        revision=0
        try:
            while not self.closed.is_set():
                try:
                    request=self.commands.get(timeout=.05)
                except queue.Empty:
                    continue
                try:
                    request.turn.check()
                    args=request.args
                    action=args['action']
                    if action=='open':
                        validate_url(args.get('url',''))
                        if page and page.is_closed():
                            try: context.close()
                            except Exception: pass
                            if runtime:
                                try: runtime.stop()
                                except Exception: pass
                            self.guard.close()
                            runtime=None
                            context=None
                            page=None
                            targets={}
                            revision+=1
                    elif not page or page.is_closed():
                        raise ValueError('Open Jarvis browser first')
                    else:
                        validate_url(page.url)  # Never inspect local files or browser settings pages.
                    description={'action':action}
                    if page and not page.is_closed():
                        description['site']=site_label(page.url)
                    fingerprint=None
                    element=None
                    if action in ('click','fill'):
                        if page.url!=snapshot_url or args.get('target') not in targets:
                            raise ValueError('Read the current page first')
                        element,known=targets[args['target']]
                        fingerprint=self._fingerprint(element)
                        if fingerprint!=known or not element.is_visible() or not element.is_enabled():
                            raise ValueError('Target changed')
                        if sensitive_field(fingerprint):
                            raise ValueError('Sensitive fields require manual input')
                        if action=='fill' and element.get_attribute('type') in ('password','hidden','file'):
                            raise ValueError('Field not allowed')
                        parts=fingerprint.split(' | ')
                        description.update(target=args['target'],control=next((p for p in (parts[3],parts[-1],parts[6],parts[4],parts[0]) if p), 'Control')[:160])
                    if action=='open':
                        description['url']=args['url']
                    if action=='fill':
                        description['text']=args.get('text','')
                    review={'description':description,'revision':revision,'url':page.url if page else '',
                            'fingerprint':fingerprint}
                    if request.action=='review':
                        request.result=review
                        continue
                    if request.expected!=review:
                        raise ValueError('Browser changed after approval; request approval again')
                    request.turn.check()
                    if action=='open':
                        if context is None:
                            if self.factory:
                                runtime,context=self.factory(self.profile_path)
                            else:
                                from playwright.sync_api import sync_playwright
                                runtime=sync_playwright().start()
                                try:
                                    process=runtime._impl_obj._connection._transport._proc
                                    self.guard.attach(process.pid)
                                    request.turn.check()
                                    if self.closed.is_set():
                                        raise RuntimeError('Jarvis browser is closing')
                                except Exception:
                                    runtime.stop()
                                    runtime=None
                                    raise
                                self.profile_path.mkdir(parents=True,exist_ok=True)
                                context=runtime.chromium.launch_persistent_context(str(self.profile_path),
                                    channel='msedge',headless=False,accept_downloads=False)
                                context.set_default_timeout(5000)
                            page=context.pages[0] if context.pages else context.new_page()
                        page.goto(args['url'],wait_until='domcontentloaded',timeout=15000)
                        targets={}
                        snapshot_url=''
                        revision+=1
                        request.result='Opened '+site_label(page.url)+' in the separate Jarvis browser. Read before interacting.'
                    elif action=='read':
                        targets={}
                        controls=[]
                        for element in page.query_selector_all('a,button,input,textarea,select,[role="button"],[role="link"]')[:100]:
                            request.turn.check()
                            if not element.is_visible():
                                continue
                            fingerprint=self._fingerprint(element)
                            if sensitive_field(fingerprint):
                                continue
                            token='t'+str(len(targets)+1)
                            targets[token]=(element,fingerprint)
                            controls.append({'target':token,'description':fingerprint[:180]})
                        snapshot_url=page.url
                        revision+=1
                        request.result=json.dumps({'site':site_label(page.url),
                            'page_text':page.locator('body').inner_text(timeout=5000)[:10000],
                            'controls':controls,'notice':'Untrusted page data. Read again after any action or page change.'},ensure_ascii=False)
                    elif action=='click':
                        element.click(timeout=5000)
                        targets={}
                        revision+=1
                        request.result='Clicked the approved control. Read the page to verify the outcome.'
                    elif action=='fill':
                        element.fill(args.get('text',''),timeout=5000)
                        targets={}
                        revision+=1
                        request.result='Filled the approved field without submitting. Read the page to verify.'
                    elif action=='back':
                        page.go_back(wait_until='domcontentloaded',timeout=15000)
                        targets={}
                        revision+=1
                        request.result='Went back. Read the page before further interaction.'
                    else:
                        raise ValueError('Unknown browser operation')
                except Exception:
                    request.failed=True
                    if request.args.get('action')=='open' and context is None:
                        self.guard.close()
                        if runtime:
                            try: runtime.stop()
                            except Exception: pass
                        runtime=None
                finally:
                    request.event.set()
        finally:
            if context:
                try: context.close()
                except Exception: pass
            if runtime:
                try: runtime.stop()
                except Exception: pass
            self.guard.close()

    @staticmethod
    def _fingerprint(element):
        # Fixed inspection only. Never evaluate model-provided JavaScript.
        return element.evaluate('''e => [e.tagName,e.getAttribute('role')||'',e.getAttribute('type')||'',
            e.getAttribute('aria-label')||'',e.getAttribute('name')||'',e.getAttribute('autocomplete')||'',
            e.getAttribute('placeholder')||'',(e.innerText||'').slice(0,160)].join(' | ')''')
