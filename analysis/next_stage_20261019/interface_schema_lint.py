"""Dependency-free lint for exactly the keyword subset used in the two contracts.
Not a general Draft7 engine. Unknown validation keywords abort rather than pass.
Reproduce: $PY analysis/next_stage_20261019/interface_schema_lint.py <schema> <value>
"""
import argparse,datetime,json,re
from pathlib import Path
ANNOTATIONS={'$schema','$id','title','description','default','examples'}
SUPPORTED=ANNOTATIONS|{'type','const','enum','required','properties','additionalProperties','items','minimum','pattern','format','oneOf'}
def validate(schema,value,path='$'):
 unknown=set(schema)-SUPPORTED
 if unknown:raise ValueError('Unsupported schema keyword: '+str(unknown))
 errors=[]
 def fail(reason):errors.append(dict(path=path,reason=reason))
 types={'object':lambda x:isinstance(x,dict),'array':lambda x:isinstance(x,list),'string':lambda x:isinstance(x,str),
 'integer':lambda x:type(x) is int,'number':lambda x:type(x) in (int,float),'boolean':lambda x:type(x) is bool,'null':lambda x:x is None}
 if 'oneOf' in schema and sum(not validate(s,value,path) for s in schema['oneOf'])!=1:fail('oneOf')
 expected=schema.get('type');expected=[expected] if isinstance(expected,str) else expected
 if expected and not any(types[t](value) for t in expected):
  fail('type '+str(expected));return errors
 if 'const' in schema and value!=schema['const']:fail('const')
 if 'enum' in schema and value not in schema['enum']:fail('enum')
 if isinstance(value,dict):
  for key in schema.get('required',[]):
   if key not in value:fail('missing '+key)
  properties=schema.get('properties',{})
  if schema.get('additionalProperties') is False:
   for key in set(value)-set(properties):fail('additional '+key)
  for key,node in properties.items():
   if key in value:errors.extend(validate(node,value[key],path+'.'+key))
 if isinstance(value,list) and 'items' in schema:
  for i,item in enumerate(value):errors.extend(validate(schema['items'],item,path+'['+str(i)+']'))
 if type(value) in (int,float) and 'minimum' in schema and value<schema['minimum']:fail('minimum')
 if isinstance(value,str):
  if 'pattern' in schema and not re.search(schema['pattern'],value):fail('pattern')
  if schema.get('format')=='date-time':
   try:datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
   except ValueError:fail('date-time')
 return errors
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('schema',type=Path);p.add_argument('value',type=Path);a=p.parse_args()
 errors=validate(json.loads(a.schema.read_text()),json.loads(a.value.read_text()))
 print(json.dumps(dict(status='failed' if errors else 'passed',errors=errors,scope='used contract keywords only; no third-party jsonschema installed'),indent=2))
 raise SystemExit(bool(errors))
if __name__=='__main__':main()
