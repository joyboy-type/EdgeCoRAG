"""Archive/checksum results, await off-machine backup, then stop current instance."""
import os,time,json,hashlib,tarfile,subprocess,sys,shutil
from pathlib import Path
O=Path('/root/autodl-tmp/registered-20261024');base=O.parent
while not (O/'session_finished.json').exists():time.sleep(5)
code=O/'code';code.mkdir(exist_ok=True)
for name in ('supplement_core.py','encode_queries.py','generate_equal_count.py','cost_generator_rpc.py','measure_cost.py','compress_dimensions.py','run_session.py','finalize_session.py'):
 p=Path('/root')/name
 if p.exists():shutil.copy2(p,code/name)
manifest={str(p.relative_to(O)):hashlib.sha256(p.read_bytes()).hexdigest() for p in O.rglob('*') if p.is_file()};(O/'file_sha256.json').write_text(json.dumps(manifest,indent=2));os.sync()
archive=base/'registered-20261024-results.tar.gz'
with tarfile.open(archive,'w:gz') as t:t.add(O,arcname=O.name)
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
with tarfile.open(archive,'r:gz') as t:
 assert len(t.getmembers())>len(manifest)
(archive.with_suffix(archive.suffix+'.sha256')).write_text(digest+'  '+archive.name+'\n');os.sync()
(O/'archive_ready.json').write_text(json.dumps({'archive':str(archive),'sha256':digest,'bytes':archive.stat().st_size,'epoch':time.time()}));os.sync()
# Local watcher verifies the archive and acknowledges its exact digest.
start=time.time()
while time.time()-start<600:
 ack=O/'off_machine_backup_ack.json'
 if ack.exists() and json.loads(ack.read_text()).get('sha256')==digest:break
 time.sleep(2)
else:
 (O/'backup_warning.json').write_text(json.dumps({'warning':'Off-machine ack absent after 600s; verified archive retained on persistent data disk','epoch':time.time()}))
(O/'shutdown_receipt.json').write_text(json.dumps({'status':'issuing_shutdown','archive_sha256':digest,'off_machine_ack':(O/'off_machine_backup_ack.json').exists(),'epoch':time.time()}));os.sync()
try:
 p=subprocess.run(['shutdown','-h','now'],capture_output=True,text=True,timeout=15)
 if p.returncode==0:sys.exit(0)
except Exception:pass
# Discover this container's supervisor dynamically; never reuse a prior session pid.
sys.path.insert(0,'/root/autodl-tmp/session/code/b-side')
import boot_watchdog
pid=boot_watchdog.supervisor_pid()
(O/'shutdown_receipt.json').write_text(json.dumps({'status':'platform_supervisor_shutdown','supervisor_pid':pid,'archive_sha256':digest,'off_machine_ack':(O/'off_machine_backup_ack.json').exists(),'epoch':time.time()}));os.sync();boot_watchdog.shutdown()
