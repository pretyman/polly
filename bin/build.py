#!/usr/bin/env python3

# Copyright (c) 2014-2015, Ruslan Baratov
# All rights reserved.

import argparse
import os
import platform
import shutil
import sys

import detail.call
import detail.cpack_generator
import detail.create_framework
import detail.generate_command
import detail.get_nmake_environment
import detail.ios_dev_root
import detail.logging
import detail.open_project
import detail.osx_dev_root
import detail.pack_command
import detail.test_command
import detail.toolchain_name
import detail.toolchain_table
import detail.verify_mingw_path
import detail.verify_msys_path

toolchain_table = detail.toolchain_table.toolchain_table

assert(sys.version_info.major == 3)
assert(sys.version_info.minor >= 2) # Current cygwin version is 3.2.3

description="""
Script for building. Available toolchains:\n
"""

for x in toolchain_table:
  description += '  ' + x.name + '\n'

parser = argparse.ArgumentParser(
    formatter_class=argparse.RawDescriptionHelpFormatter,
    description=description
)

parser.add_argument(
    '--toolchain',
    choices=[x.name for x in toolchain_table],
    help="CMake generator/toolchain",
)

parser.add_argument(
    '--config',
    help="CMake build type (Release, Debug, ...)",
)

parser.add_argument(
    '--home',
    help="Project home directory (directory with CMakeLists.txt)"
)

parser.add_argument('--test', action='store_true', help="Run ctest after build")
parser.add_argument('--pack', action='store_true', help="Run cpack after build")
parser.add_argument(
    '--nobuild', action='store_true', help="Do not build (only generate)"
)
parser.add_argument(
    '--open', action='store_true', help="Open generated project (for IDE)"
)
parser.add_argument('--verbose', action='store_true', help="Verbose output")
parser.add_argument(
    '--install', action='store_true', help="Run install (local directory)"
)
parser.add_argument(
    '--framework', action='store_true', help="Create framework"
)
parser.add_argument(
    '--clear',
    action='store_true',
    help="Remove build and install dirs before build"
)
parser.add_argument(
    '--reconfig',
    action='store_true',
    help="Run configure even if CMakeCache.txt exists. Used to add new args."
)
parser.add_argument(
    '--fwd',
    nargs='*',
    help="Arguments to cmake without '-D', like:\nBOOST_ROOT=/some/path"
)
parser.add_argument(
    '--iossim',
    action='store_true',
    help="Build for ios i386 simulator"
)

parser.add_argument(
    '--jobs',
    type=int,
    help="Number of concurrent build operations"
)

args = parser.parse_args()

polly_toolchain = detail.toolchain_name.get(args.toolchain)
toolchain_entry = detail.toolchain_table.get_by_name(polly_toolchain)
cpack_generator = detail.cpack_generator.get(args.pack)

polly_root = os.path.join(os.path.dirname(os.path.realpath(__file__)), '..')
polly_root = os.path.realpath(polly_root)

"""Build directory tag"""
if args.config and not toolchain_entry.multiconfig:
  build_tag = "{}-{}".format(polly_toolchain, args.config)
else:
  build_tag = polly_toolchain

"""Tune environment"""
if toolchain_entry.name == 'mingw':
  mingw_path = os.getenv("MINGW_PATH")
  detail.verify_mingw_path.verify(mingw_path)
  os.environ['PATH'] = "{};{}".format(mingw_path, os.getenv('PATH'))

if toolchain_entry.name == 'msys':
  msys_path = os.getenv("MSYS_PATH")
  detail.verify_msys_path.verify(msys_path)
  os.environ['PATH'] = "{};{}".format(msys_path, os.getenv('PATH'))

if toolchain_entry.is_nmake:
  os.environ = detail.get_nmake_environment.get(
      toolchain_entry.arch, toolchain_entry.vs_version
  )

if toolchain_entry.ios_version:
  ios_dev_root = detail.ios_dev_root.get(toolchain_entry.ios_version)
  if ios_dev_root:
    print("Set environment DEVELOPER_DIR to {}".format(ios_dev_root))
    os.environ['DEVELOPER_DIR'] = ios_dev_root

if toolchain_entry.name == 'ios-nocodesign':
  xcconfig = os.path.join(polly_root, 'scripts', 'NoCodeSign.xcconfig')
  print("Set environment XCODE_XCCONFIG_FILE to {}".format(xcconfig))
  os.environ['XCODE_XCCONFIG_FILE'] = xcconfig

if toolchain_entry.osx_version:
  osx_dev_root = detail.osx_dev_root.get(toolchain_entry.osx_version)
  if osx_dev_root:
    print("Set environment DEVELOPER_DIR to {}".format(osx_dev_root))
    os.environ['DEVELOPER_DIR'] = osx_dev_root

cdir = os.getcwd()

toolchain_path = os.path.join(polly_root, "{}.cmake".format(polly_toolchain))
if not os.path.exists(toolchain_path):
  sys.exit("Toolchain file not found: {}".format(toolchain_path))
toolchain_option = "-DCMAKE_TOOLCHAIN_FILE={}".format(toolchain_path)

build_dir = os.path.join(cdir, '_builds', build_tag)
print("Build dir: {}".format(build_dir))
build_dir_option = "-B{}".format(build_dir)

install_dir = os.path.join(cdir, '_install', polly_toolchain)
local_install = args.install or args.framework
if local_install:
  install_dir_option = "-DCMAKE_INSTALL_PREFIX={}".format(install_dir)

if args.framework and platform.system() != 'Darwin':
  sys.exit('Framework creation only for Mac OS X')
framework_dir = os.path.join(cdir, '_framework', polly_toolchain)

if args.clear:
  if os.path.exists(build_dir):
    print("Remove build directory: {}".format(build_dir))
    shutil.rmtree(build_dir)
  if os.path.exists(install_dir):
    print("Remove install directory: {}".format(install_dir))
    shutil.rmtree(install_dir)
  if os.path.exists(framework_dir):
    print("Remove framework directory: {}".format(framework_dir))
    shutil.rmtree(framework_dir)
  if os.path.exists(build_dir):
    sys.exit("Directory removing failed ({})".format(build_dir))
  if os.path.exists(install_dir):
    sys.exit("Directory removing failed ({})".format(install_dir))
  if os.path.exists(framework_dir):
    sys.exit("Directory removing failed ({})".format(framework_dir))

polly_temp_dir = os.path.join(build_dir, '_3rdParty', 'polly')
if not os.path.exists(polly_temp_dir):
  os.makedirs(polly_temp_dir)
logging = detail.logging.Logging(polly_temp_dir, args.verbose)

if os.name == 'nt':
  # Windows
  detail.call.call(['where', 'cmake'], logging)
else:
  detail.call.call(['which', 'cmake'], logging)
detail.call.call(['cmake', '--version'], logging)

home = '.'
if args.home:
  home = args.home

generate_command = [
    'cmake',
    '-H{}'.format(home),
    build_dir_option
]

if toolchain_entry.vs_version and args.jobs:
  generate_command.append("-DPOLLY_PARALLEL=YES")

if args.config and not toolchain_entry.multiconfig:
  generate_command.append("-DCMAKE_BUILD_TYPE={}".format(args.config))

if toolchain_entry.generator:
  generate_command.append('-G{}'.format(toolchain_entry.generator))

if toolchain_entry.xp:
  toolset = 'v{}0_xp'.format(toolchain_entry.vs_version)
  generate_command.append('-T{}'.format(toolset))

if toolchain_option:
  generate_command.append(toolchain_option)

generate_command.append('-DCMAKE_VERBOSE_MAKEFILE=ON')
generate_command.append('-DPOLLY_STATUS_DEBUG=ON')
generate_command.append('-DHUNTER_STATUS_DEBUG=ON')

if local_install:
  generate_command.append(install_dir_option)

if cpack_generator:
  generate_command.append('-DCPACK_GENERATOR={}'.format(cpack_generator))

if args.fwd != None:
  for x in args.fwd:
    generate_command.append("-D{}".format(x))

detail.generate_command.run(
    generate_command, build_dir, polly_temp_dir, args.reconfig, logging
)

build_command = [
    'cmake',
    '--build',
    build_dir
]

if args.config:
  build_command.append('--config')
  build_command.append(args.config)

if local_install:
  build_command.append('--target')
  build_command.append('install')

# NOTE: This must be the last `build_command` modification!
build_command.append('--')

if args.iossim:
  build_command.append('-arch')
  build_command.append('i386')
  build_command.append('-sdk')
  build_command.append('iphonesimulator')

if args.jobs:
  if toolchain_entry.is_xcode:
    build_command.append('-jobs')
    build_command.append('{}'.format(args.jobs))
  elif toolchain_entry.is_make and not toolchain_entry.is_nmake:
    build_command.append('-j')
    build_command.append('{}'.format(args.jobs))

if not args.nobuild:
  detail.call.call(build_command, logging)
  if args.framework:
    detail.create_framework.run(
        install_dir,
        framework_dir,
        toolchain_entry.ios_version,
        polly_root,
        logging
    )

if not args.nobuild:
  os.chdir(build_dir)
  if args.test:
    detail.test_command.run(build_dir, args.config, logging)
  if args.pack:
    detail.pack_command.run(args.config, logging, cpack_generator)

if args.open:
  detail.open_project.open(toolchain_entry, build_dir, logging)

print('Log saved: {}'.format(logging.log_path))
print('SUCCESS')
