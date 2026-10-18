"""Only the new delivery guard is tested; previous application tests are reused."""
import unittest
import nestopia_delivery as gate
class Delivery(unittest.TestCase):
 def records(self):
  rows=[dict(label='baseline',filter='composite',cppAllocationsPoisoned=1,faultOffset='0x45cc8',log='CONTENT_LOADED',fault='fatal signal=0xb')]
  rows += [dict(label='fixed',filter=f,cppAllocationsPoisoned=1,log='frames=120\nEXIT=0',fault='') for f in ('composite','svideo','rgb','monochrome','disabled')]
  core=dict(result='passed',source=gate.CORE_REF,physicalDeviceValidated=False,baselineMatchesDeviceFault=True,results=rows)
  skin=dict(result='passed',source=gate.CORE_REF,sessions=6,failures=[],cppPoisonLogEntries=8,physicalDeviceValidated=False,outcome={'finished':True})
  return core,skin
 def test_complete_witness_and_closed_change_scope(self):
  core,skin=self.records();self.assertEqual(gate.validate_verdicts(core,skin)['core'],core)
  gate.validate_changed_paths(['AGENTS.md','.github/workflows/retroarch-delivery.yml'])
  for path in ['packages/libretro_internal_bridge/ios/Classes/LibretroSession.m','native/nestopia/reset-background.patch','lib/main.dart','.github/diagnostics/nestopia_bgcolor/probe.py']:
   with self.assertRaisesRegex(ValueError,'Unvalidated'):gate.validate_changed_paths([path])
 def test_baseline_must_match_observed_device_fault(self):
  for key,value in [('faultOffset','0x123'),('fault',''),('cppAllocationsPoisoned',0),('log','FIRST_FRAME')]:
   core,skin=self.records();core['results'][0][key]=value
   with self.assertRaises(ValueError):gate.validate_verdicts(core,skin)
 def test_reject_partial_or_failed_fixed_modes(self):
  for kind in ('missing','frame','fault','poison','source'):
   core,skin=self.records()
   if kind=='missing':core['results'].pop()
   elif kind=='frame':core['results'][-1]['log']='frames=1\nEXIT=0'
   elif kind=='fault':core['results'][-1]['fault']='fatal signal=0xb'
   elif kind=='poison':core['results'][-1]['cppAllocationsPoisoned']=0
   else:core['source']='other'
   with self.assertRaises(ValueError):gate.validate_verdicts(core,skin)
 def test_reject_incomplete_skin_and_false_hardware_claim(self):
  for key,value in [('sessions',5),('failures',['failed']),('cppPoisonLogEntries',0),('physicalDeviceValidated',True),('outcome',{'finished':False})]:
   core,skin=self.records();skin[key]=value
   with self.assertRaises(ValueError):gate.validate_verdicts(core,skin)
if __name__=='__main__':unittest.main()
