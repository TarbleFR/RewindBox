import importlib.util
from pathlib import Path
import sys
import unittest
from datetime import datetime, timezone, timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'build-utils/maintenance'))
import retire_obsolete_actions as m

class Fake:
    def __init__(self):
        self.entry={'id':1,'sha':'a'*40,'path':'.github/workflows/rewind610-delivery.yml','created_at':(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()}
        self.run={**self.entry,'head_sha':'a'*40,'run_attempt':1,'status':'queued','conclusion':None}
        self.jobs=[];self.artifacts=[];self.posts=[]
    def request(self,path,method='GET'):
        if method=='POST':
            self.posts.append(path);self.run.update(status='completed',conclusion='cancelled');return None
        if '/artifacts?' in path:return {'total_count':len(self.artifacts),'artifacts':self.artifacts}
        if '/jobs?' in path:return {'total_count':len(self.jobs),'jobs':self.jobs}
        return self.run.copy()

class Retirement(unittest.TestCase):
    def test_queued_empty_old_run_cancelled_and_confirmed(self):
        a=Fake();self.assertEqual(m.cancel(a,a.entry,lambda _:None),'cancelled');self.assertEqual(len(a.posts),1)
    def test_never_cancel_started_changed_attempt_artifact_or_executed_job(self):
        for field,value in (('status','in_progress'),('run_attempt',2),('head_sha','b'*40)):
            a=Fake();a.run[field]=value
            with self.assertRaises(RuntimeError):m.cancel(a,a.entry,lambda _:None)
            self.assertEqual(a.posts,[])
        for field,value in (('artifacts',[{'id':7}]),('jobs',[{'status':'completed','conclusion':'success','steps':[{'name':'work'}]}])):
            a=Fake();setattr(a,field,value)
            with self.assertRaises(RuntimeError):m.cancel(a,a.entry,lambda _:None)
            self.assertEqual(a.posts,[])
    def test_terminal_and_recent_runs_do_not_get_cancelled(self):
        a=Fake();a.run['status']='completed';self.assertEqual(m.cancel(a,a.entry),'already_completed');self.assertEqual(a.posts,[])
        a=Fake();a.entry['created_at']=a.run['created_at']=datetime.now(timezone.utc).isoformat()
        with self.assertRaises(RuntimeError):m.cancel(a,a.entry,lambda _:None)
        self.assertEqual(a.posts,[])
    def test_changed_identity_between_checks_stops_before_post(self):
        a=Fake();old=a.request;count=0
        def read(path,method='GET'):
            nonlocal count
            if path.endswith('/runs/1'):
                count+=1
                if count==2:a.run['status']='in_progress'
            return old(path,method)
        a.request=read
        with self.assertRaises(RuntimeError):m.cancel(a,a.entry,lambda _:None)
        self.assertEqual(a.posts,[])
    def test_force_cancel_only_after_fresh_unchanged_empty_inventory(self):
        for changed in (None,'artifact','job','head','running'):
            a=Fake();old=a.request
            def read(path,method='GET'):
                if method=='POST' and path.endswith('/cancel'):
                    a.posts.append(path)
                    if changed=='artifact':a.artifacts=[{'id':5}]
                    if changed=='job':a.jobs=[{'status':'completed','conclusion':'success','steps':[{'name':'work'}]}]
                    if changed=='head':a.run['head_sha']='b'*40
                    if changed=='running':a.run['status']='in_progress'
                    return None
                return old(path,method)
            a.request=read
            if changed:
                with self.assertRaises(RuntimeError):m.cancel(a,a.entry,lambda _:None)
                self.assertEqual(len(a.posts),1)
            else:
                self.assertEqual(m.cancel(a,a.entry,lambda _:None),'cancelled')
                self.assertEqual(len(a.posts),2)
                self.assertTrue(a.posts[-1].endswith('/force-cancel'))
    def test_run_starting_during_job_inventory_is_preserved(self):
        a=Fake();old=a.request;inventories=0
        def read(path,method='GET'):
            nonlocal inventories
            result=old(path,method)
            if '/jobs?' in path:
                inventories+=1
                if inventories==2:a.run['status']='in_progress'
            return result
        a.request=read
        with self.assertRaises(RuntimeError):m.cancel(a,a.entry,lambda _:None)
        self.assertEqual(a.posts,[])
if __name__=='__main__':unittest.main()
