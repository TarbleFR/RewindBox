#!/usr/bin/env python3
"""Public-file boundaries for Yandex CI verification; no account or network used."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/textures'))
import hosts  # noqa: E402


class PublicFileTest(unittest.TestCase):
    url = 'https://disk.yandex.ru/d/creator-file'
    metadata = {'type': 'file', 'name': 'replacements.7z', 'size': 8, 'sha256': 'abc'}
    link = {'href': 'https://downloader.disk.yandex.ru/file/temporary-signature'}

    def pages(self, metadata=None, link=None):
        return patch.object(hosts, '_page', side_effect=[
            (json.dumps(self.metadata if metadata is None else metadata), ''),
            (json.dumps(self.link if link is None else link), ''),
        ])

    def test_original_file_preserves_name_and_drops_temporary_url(self):
        with self.pages(), patch.object(hosts, '_download_direct', return_value={
                'size': 8, 'sha256': 'abc', 'name': 'temporary', 'final': self.link['href']}) as fetch:
            result = hosts.yandex(self.url, 'destination', 8)
        self.assertEqual(result, {'size': 8, 'sha256': 'abc', 'name': 'replacements.7z'})
        fetch.assert_called_once_with(self.link['href'], 'destination', 8)

    def test_non_files_and_oversize_stop_before_download_endpoint(self):
        for metadata, status in [({'type': 'dir'}, 'unsupported'),
                                 ({**self.metadata, 'size': 9}, 'tooLarge'),
                                 ({'error': 'DiskResourceNotFoundError'}, 'protected')]:
            with self.subTest(metadata=metadata), self.pages(metadata) as pages, \
                    patch.object(hosts, '_download_direct') as fetch:
                with self.assertRaises(hosts.HostError) as caught:
                    hosts.yandex(self.url, 'destination', 8)
                self.assertEqual(caught.exception.status, status)
                self.assertEqual(pages.call_count, 1)
                fetch.assert_not_called()

    def test_quota_and_permission_stop_without_retry_or_copy(self):
        for error, status in [('DiskDownloadLimitExceededError', 'quota'),
                              ('DiskForbiddenError', 'protected')]:
            with self.subTest(error=error), self.pages(link={'error': error}), \
                    patch.object(hosts, '_download_direct') as fetch:
                with self.assertRaises(hosts.HostError) as caught:
                    hosts.yandex(self.url, 'destination', 8)
                self.assertEqual(caught.exception.status, status)
                fetch.assert_not_called()

    def test_http_quota_propagates(self):
        with patch.object(hosts, '_page', side_effect=hosts.HostError('quota', 'HTTP 429')) as pages:
            with self.assertRaises(hosts.HostError) as caught:
                hosts.yandex(self.url, 'destination', 8)
            self.assertEqual(caught.exception.status, 'quota')
            pages.assert_called_once()

    def test_only_provider_https_downloads_are_accepted(self):
        for href in ['', 'http://downloader.disk.yandex.ru/file', 'https://example.org/file',
                     'https://yandex.ru.example.org/file', 'https://user@downloader.disk.yandex.ru/file']:
            with self.subTest(href=href), self.pages(link={'href': href}), \
                    patch.object(hosts, '_download_direct') as fetch:
                with self.assertRaises(hosts.HostError) as caught:
                    hosts.yandex(self.url, 'destination', 8)
                self.assertEqual(caught.exception.status, 'unsupported')
                fetch.assert_not_called()

    def test_changed_file_is_refused(self):
        with self.pages(), patch.object(hosts, '_download_direct', return_value={'sha256': 'different'}):
            with self.assertRaises(hosts.HostError) as caught:
                hosts.yandex(self.url, 'destination', 8)
            self.assertEqual(caught.exception.status, 'changed')

    def test_stream_bound_is_not_relaxed(self):
        with self.pages(), patch.object(hosts, '_download_direct',
                                      side_effect=hosts.HostError('tooLarge', 'stream exceeds bound')):
            with self.assertRaises(hosts.HostError) as caught:
                hosts.yandex(self.url, 'destination', 8)
            self.assertEqual(caught.exception.status, 'tooLarge')


if __name__ == '__main__':
    unittest.main()
