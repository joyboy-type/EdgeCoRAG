"""New-run recording only. No model imports; no backfilling historical receipts."""
import hashlib
import math
from pathlib import Path
import threading

def redacted_prompt(rendered,messages):
    if not isinstance(rendered,str):raise ValueError('Processor must return actual string')
    secrets=[]
    for message in messages:
        for part in message.get('content',[]):
            for key in ('text','image','url'):
                if isinstance(part.get(key),str) and part[key]:secrets.append(part[key])
    text=rendered
    for secret in sorted(set(secrets),key=len,reverse=True):text=text.replace(secret,'[REDACTED_CONTENT]')
    # Persist only chat-template structure. Unknown multimodal expansions are not published.
    if any(marker in text for marker in ('data:image','file://','/Users/','/root/')):
        text='[REDACTED_RENDERED_PROMPT]'
    return dict(status='recorded_redacted',text=text,original_sha256=hashlib.sha256(rendered.encode()).hexdigest(),
                policy='all message text and image locations removed; fingerprint of original UTF-8 string')

def system_memory(read):
    text=read('/proc/meminfo');values={}
    for line in text.splitlines():
        parts=line.split()
        if len(parts)>=2 and parts[0] in ('MemTotal:','MemAvailable:'):
            values[parts[0][:-1]]=int(parts[1])*1024
    total,available=values['MemTotal'],values['MemAvailable']
    if not 0<=available<=total or total<=0:raise ValueError('Invalid host memory counters')
    return total,total-available

class ResourceSampler:
    """20ms host/device samples; maxima are sampled lower bounds, never exact peaks."""
    def __init__(self,device=None,*,meminfo=None,interval=.02):
        self.device=device;self.meminfo=meminfo or (lambda name:Path(name).read_text())
        self.interval=interval;self.device_values=[];self.host_values=[];self.errors=set()
        self.stop=threading.Event();self.worker=None
    def sample(self):
        if self.device is not None:
            try:
                row=self.device();used=row['used_bytes'];total=row['total_bytes']
                if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in (used,total)) or not 0<=used<=total or total<=0:
                    raise ValueError('Invalid device-wide memory sample')
                self.device_values.append(float(used))
            except Exception as e:self.errors.add('device:'+type(e).__name__)
        try:self.host_values.append(system_memory(self.meminfo))
        except Exception as e:self.errors.add('host:'+type(e).__name__)
    def start(self):
        self.sample()
        if self.device is not None:
            def loop():
                while not self.stop.wait(self.interval):self.sample()
            self.worker=threading.Thread(target=loop,daemon=True);self.worker.start()
        return self
    def finish(self):
        self.stop.set()
        if self.worker:self.worker.join()
        device=dict(status='not_measured',reason='no valid device-wide sampler observation')
        if self.device_values:
            device=dict(status='sampled',value=max(self.device_values)/1024**3,unit='GiB',
                samples=len(self.device_values),interval_seconds=self.interval,
                scope='device-wide used memory; max sampled lower bound, not exact peak or allocator')
        host=dict(status='not_measured',reason='no valid /proc/meminfo observation')
        if self.host_values:
            host=dict(status='sampled',max_used_bytes=max(v[1] for v in self.host_values),
                      total_bytes=max(v[0] for v in self.host_values),samples=len(self.host_values),
                      scope='host/system total minus MemAvailable; container and other workloads may contribute')
        return dict(peak_vram_gb=device,system_ram=host,
                    energy=dict(status='not_measured',value=None,unit='J',reason='no calibrated power/energy instrument'),
                    sampling_errors=sorted(self.errors))
