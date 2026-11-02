#!/usr/bin/env python3
"""Exercise actual installer archive paths without executing package managers."""
import io
from importlib.machinery import SourceFileLoader
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/jenkins'))
import control
toolchain=SourceFileLoader('unpack_toolchain',str(ROOT/'scripts/jenkins/toolchain.py')).load_module()

class UnpackTests(unittest.TestCase):
    def test_provider_binary_executes_and_other_files_are_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);source=directory/'provider.zip';target=directory/'mirror';target.mkdir()
            with zipfile.ZipFile(source,'w') as archive:
                # The ZIP writer's default permissions have no execute bit.
                archive.writestr('terraform-provider-fixture_v1.2.3_x5','#!/bin/sh\nprintf fixture-provider')
                archive.writestr('LICENSE.txt','synthetic license')
            toolchain.unpack_provider(source,target,'fixture','1.2.3')
            binary=target/'terraform-provider-fixture_v1.2.3_x5'
            self.assertEqual(stat.S_IMODE(binary.stat().st_mode),0o555)
            self.assertEqual(stat.S_IMODE((target/'LICENSE.txt').stat().st_mode),0o444)
            self.assertEqual(subprocess.check_output([str(binary)],text=True),'fixture-provider')
    def node_archive(self,source,extra=None):
        root='node-v22.23.3-linux-x64'
        with tarfile.open(source,'w:xz') as archive:
            entry=tarfile.TarInfo(root);entry.type=tarfile.DIRTYPE;archive.addfile(entry)
            for name,content,mode in [('bin/node',b'#!/bin/sh\nprintf v22.23.3',0o755),('lib/node_modules/npm/bin/npm-cli.js',b'fixture',0o644)]:
                entry=tarfile.TarInfo(root+'/'+name);entry.mode=mode;entry.size=len(content);archive.addfile(entry,io.BytesIO(content))
            entry=tarfile.TarInfo(root+'/bin/npm');entry.type=tarfile.SYMTYPE;entry.linkname='../lib/node_modules/npm/bin/npm-cli.js';archive.addfile(entry)
            if extra:archive.addfile(extra)
        return root
    def test_official_node_structure_root_and_fixed_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);source=directory/'node.tar.xz';target=directory/'node'
            root=self.node_archive(source);toolchain.unpack_node(source,target,root)
            self.assertEqual(subprocess.check_output([str(target/'bin/node')],text=True),'v22.23.3')
            self.assertFalse((target/'bin/npm').exists())
            self.assertEqual(stat.S_IMODE((target/'lib/node_modules/npm/bin/npm-cli.js').stat().st_mode),0o444)
    def test_node_traversal_and_unexpected_links_refused(self):
        for name,kind in [('node-v22.23.3-linux-x64/../escape',tarfile.REGTYPE),('node-v22.23.3-linux-x64/bin/evil',tarfile.SYMTYPE),('foreign-root',tarfile.DIRTYPE)]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temporary:
                directory=Path(temporary);entry=tarfile.TarInfo(name);entry.type=kind;entry.linkname='/etc/passwd'
                root=self.node_archive(directory/'node.tar.xz',entry)
                with self.assertRaises(control.Refused):toolchain.unpack_node(directory/'node.tar.xz',directory/'node',root)
    def test_unexpected_provider_executable_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            with zipfile.ZipFile(directory/'provider.zip','w') as archive:archive.writestr('terraform-provider-other_v1.2.3','bad')
            with self.assertRaises(control.Refused):toolchain.unpack_provider(directory/'provider.zip',directory/'mirror','fixture','1.2.3')

if __name__=='__main__':unittest.main()
