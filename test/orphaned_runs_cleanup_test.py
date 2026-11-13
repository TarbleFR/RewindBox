import sys
from pathlib import Path
from unittest.mock import Mock, call, patch
import unittest
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'build-utils/maintenance'))
import remove_orphaned_runs as m
class Tests(unittest.TestCase):
    def test_ineligible_or_completed_is_never_deleted(self):
        for outcome in (False,RuntimeError('started')):
            with patch.object(m,'eligible',return_value=outcome if outcome is False else None,side_effect=outcome if isinstance(outcome,Exception) else None):
                with patch.object(m,'API') as api:
                    with patch.object(api,'delete') as delete:
                        if isinstance(outcome,Exception):
                            with self.assertRaises(RuntimeError):m.remove(api,{'id':1},delete)
                        else:self.assertEqual(m.remove(api,{'id':1},delete),'completed_preserved')
                        delete.assert_not_called()
    def test_delete_requires_absence_confirmation(self):
        for status,expected in ((404,'deleted_confirmed'),(None,'deletion_not_confirmed')):
            with patch.object(m,'eligible',return_value=True),patch.object(m,'API') as api:
                api.request.side_effect=HTTPError('u',status,'not found',{},None) if status else None
                with patch.object(api,'delete') as delete:
                    self.assertEqual(m.remove(api,{'id':1},delete,sleep=lambda _: None),expected)
                    delete.assert_called_once_with(m.PREFIX+'/actions/runs/1')
    def test_rejection_is_not_success_or_retried(self):
        with patch.object(m,'eligible',return_value=True),patch.object(m,'API') as api:
            with patch.object(api,'delete',side_effect=HTTPError('u',409,'conflict',{},None)) as delete:
                self.assertEqual(m.remove(api,{'id':1},delete),'delete_refused_409')
                self.assertEqual(delete.call_count,1)
    def test_preexisting_absence_is_not_counted_as_our_deletion(self):
        with patch.object(m,'eligible',return_value=True),patch.object(m,'API') as api:
            api.request.side_effect=HTTPError('u',404,'not found',{},None)
            with patch.object(api,'delete',side_effect=HTTPError('u',404,'not found',{},None)):
                self.assertEqual(m.remove(api,{'id':1},api.delete),'already_absent_confirmed')
    def test_eventual_absence_polls_get_without_repeating_delete(self):
        with patch.object(m,'eligible',return_value=True),patch.object(m,'API') as api:
            api.request.side_effect=[{'status':'queued'}, {'status':'queued'}, HTTPError('u',404,'not found',{},None)]
            sleep=Mock()
            with patch.object(api,'delete') as delete:
                self.assertEqual(m.remove(api,{'id':1},delete,sleep=sleep),'deleted_confirmed')
                delete.assert_called_once_with(m.PREFIX+'/actions/runs/1')
            self.assertEqual(api.request.call_count,3)
            self.assertEqual(sleep.call_args_list,[call(m.CONFIRMATION_DELAY_SECONDS)]*2)
    def test_confirmation_stops_at_bound_without_another_mutation(self):
        with patch.object(m,'eligible',return_value=True),patch.object(m,'API') as api:
            api.request.return_value={'status':'queued'}
            sleep=Mock()
            with patch.object(api,'delete') as delete:
                self.assertEqual(m.remove(api,{'id':1},delete,sleep=sleep),'deletion_not_confirmed')
                delete.assert_called_once()
            self.assertEqual(api.request.call_count,m.CONFIRMATION_ATTEMPTS)
            self.assertEqual(sleep.call_count,m.CONFIRMATION_ATTEMPTS-1)
    def test_confirmation_authorization_failure_stops_immediately(self):
        with patch.object(m,'eligible',return_value=True),patch.object(m,'API') as api:
            api.request.side_effect=HTTPError('u',403,'forbidden',{},None)
            sleep=Mock()
            with patch.object(api,'delete') as delete:
                with self.assertRaises(HTTPError):m.remove(api,{'id':1},delete,sleep=sleep)
                delete.assert_called_once()
            sleep.assert_not_called()
if __name__=='__main__':unittest.main()
