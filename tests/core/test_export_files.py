"""Atomic exports use disposable paths and preserve both source and old destination."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import export_files


class ExportFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.source=self.folder/'生成源.wav';self.source.write_bytes(b'new audio'*1000)
        self.target=self.folder/'中文 export.wav';self.target.write_bytes(b'old export')

    def tearDown(self):self.temp.cleanup()

    def check_old(self):
        self.assertEqual(self.source.read_bytes(),b'new audio'*1000)
        self.assertEqual(self.target.read_bytes(),b'old export')
        self.assertEqual(list(self.folder.glob('.emoblocks-export-*')),[])

    def test_overwrite_is_complete_with_unicode_spaces_and_long_directory(self):
        folder=self.folder/('较长路径 English '*8);folder.mkdir();target=folder/'导出 成品.wav'
        target.write_bytes(b'old')
        result=export_files.atomic_export(self.source,target,[self.source])
        self.assertEqual(result,target.resolve());self.assertEqual(target.read_bytes(),self.source.read_bytes())
        self.assertEqual(list(folder.glob('.emoblocks-export-*')),[])

    def test_partial_copy_flush_and_replace_failures_preserve_existing_target(self):
        def partial(src,dst):dst.write(b'incomplete');raise OSError('copy failed')
        for method,effect in (('shutil.copyfileobj',partial),('os.fsync',OSError('disk full')),('os.replace',PermissionError('denied'))):
            with self.subTest(method=method),patch('export_files.'+method,side_effect=effect):
                with self.assertRaises(OSError):export_files.atomic_export(self.source,self.target,[])
            self.check_old()
        with patch('export_files.tempfile.NamedTemporaryFile',side_effect=PermissionError('unwritable directory')):
            with self.assertRaises(OSError):export_files.atomic_export(self.source,self.target,[])
        self.check_old()

    def test_missing_or_changed_source_does_not_replace_target(self):
        with self.assertRaises(FileNotFoundError):export_files.atomic_export(self.folder/'missing.wav',self.target,[])
        original=export_files.shutil.copyfileobj
        def removed(src,dst):original(src,dst);self.source.unlink()
        with patch('export_files.shutil.copyfileobj',side_effect=removed):
            with self.assertRaises(FileNotFoundError):export_files.atomic_export(self.source,self.target,[])
        self.assertEqual(self.target.read_bytes(),b'old export')
        self.assertEqual(list(self.folder.glob('.emoblocks-export-*')),[])

    def test_source_self_aliases_and_other_version_are_protected(self):
        other=self.folder/'other.mid';other.write_bytes(b'other version')
        hard=self.folder/'hard.wav';os.link(self.source,hard)
        candidates=[self.source,hard,other]
        link=self.folder/'alias.wav'
        try:link.symlink_to(self.source);candidates.append(link)
        except OSError:pass  # Windows can require a privilege for symlink creation.
        for target in candidates:
            with self.subTest(target=target),self.assertRaises(ValueError):export_files.atomic_export(self.source,target,[other])
        self.check_old();self.assertEqual(other.read_bytes(),b'other version')

    def test_failure_only_removes_its_own_temporary_file(self):
        sentinel=self.folder/'.emoblocks-export-user.tmp';sentinel.write_bytes(b'not ours')
        with patch('export_files.os.replace',side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):export_files.atomic_export(self.source,self.target,[])
        self.assertEqual(sentinel.read_bytes(),b'not ours')
        self.assertEqual(self.target.read_bytes(),b'old export')
        self.assertEqual(list(self.folder.glob('.emoblocks-export-*')),[sentinel])
