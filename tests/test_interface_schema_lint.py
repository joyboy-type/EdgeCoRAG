import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'analysis/next_stage_20261019'))
from interface_schema_lint import validate
class SchemaLint(unittest.TestCase):
 def test_unknown_nullable_boolean_is_not_guessed_false(self):
  self.assertTrue(validate({'type':'boolean'},None))
  self.assertFalse(validate({'type':['boolean','null']},None))
 def test_unfixed_or_positive_integer_but_not_boolean(self):
  schema={'oneOf':[{'type':'integer','minimum':1},{'type':'string','enum':['unfixed']}]}
  for value in [8,'unfixed']:self.assertFalse(validate(schema,value))
  for value in [True,0,'auto']:self.assertTrue(validate(schema,value))
 def test_unsupported_keyword_refuses_to_pass(self):
  with self.assertRaises(ValueError):validate({'not':{}},None)
