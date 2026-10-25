"""Sequential execution in the already authorized single GPU session."""
import subprocess,time,json
from pathlib import Path
O=Path('/root/autodl-tmp/registered-20261024');R=Path('/root/autodl-tmp/EdgeCoRAG')
start=time.time()
while not (O/'encoding_receipt.json').exists():
 if time.time()-start>600:raise RuntimeError('Encoding did not finish; inspect logs')
 time.sleep(2)
for key,env in [('qwen3vl_4b','qwen3vl'),('gemma4_e2b','gemma4'),('gemma4_e4b','gemma4'),('qwen3vl_8b','qwen3vl'),('qwen35_4b','qwen35')]:
 print(json.dumps({'stage':'equal_count','model':key,'epoch':time.time()}),flush=True)
 with (O/(key+'.log')).open('x') as f:
  p=subprocess.run([str(R/'envs'/env/'bin/python'),'-B','/root/generate_equal_count.py',key],stdout=f,stderr=subprocess.STDOUT)
 print(json.dumps({'model':key,'exit_code':p.returncode,'epoch':time.time()}),flush=True)
(O/'equal_count_finished.json').write_text(json.dumps({'epoch':time.time()}))
# Cost and compression drivers are deployed separately before reaching this point.
for script in ('measure_cost.py','compress_dimensions.py'):
 if not Path('/root',script).exists():raise RuntimeError('Next driver not deployed: '+script)
 with (O/(script+'.log')).open('x') as f:
  p=subprocess.run([str(R/'envs/gemma4/bin/python'),'-B','/root/'+script],stdout=f,stderr=subprocess.STDOUT)
 if p.returncode:print(json.dumps({'script':script,'exit_code':p.returncode}),flush=True)
(O/'session_finished.json').write_text(json.dumps({'epoch':time.time()}))
