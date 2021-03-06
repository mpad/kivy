from fnmatch import filter as fnfilter
from sys import platform, argv
from os.path import join, dirname, realpath, sep, exists
from os import walk, environ
from distutils.core import setup
from distutils.extension import Extension

try:
    # check for cython
    from Cython.Distutils import build_ext
except ImportError:
    print '\nCython is missing, its required for compiling kivy !\n\n'
    raise

# extract version (simulate doc generation, kivy will be not imported)
environ['KIVY_DOC_INCLUDE'] = '1'
import kivy

# extra build commands go in the cmdclass dict {'command-name': CommandClass}
# see tools.packaging.{platform}.build.py for custom build commands for
# portable packages.  also e.g. we use build_ext command from cython if its
# installed for c extensions.
cmdclass = {}

try:
    # add build rules for portable packages to cmdclass
    if platform == 'win32':
        from kivy.tools.packaging.win32.build import WindowsPortableBuild
        cmdclass['build_portable'] = WindowsPortableBuild
    elif platform == 'darwin':
        from kivy.tools.packaging.osx.build import OSXPortableBuild
        cmdclass['build_portable'] = OSXPortableBuild
except ImportError:
    print 'User distribution detected, avoid portable command.'

from kivy.tools.packaging.factory import FactoryBuild
cmdclass['build_factory'] = FactoryBuild

#
# Detect options
#
c_options = {
    'use_opengl_es2': True,
    'use_opengl_debug': False,
    'use_glew': False,
    'use_mesagl': 'USE_MESAGL' in environ}

# Detect which opengl version headers to use
if platform == 'win32':
    print 'Windows platform detected, force GLEW usage.'
    c_options['use_glew'] = True
elif platform == 'darwin':
    # macosx is using their own gl.h
    pass
else:
    # searching GLES headers
    default_header_dirs = ['/usr/include', '/usr/local/include']
    found = False
    for hdir in default_header_dirs:
        filename = join(hdir, 'GLES2', 'gl2.h')
        if exists(filename):
            found = True
            print 'Found GLES 2.0 headers at', filename
            break
    if not found:
        print 'WARNING: GLES 2.0 headers are not found'
        print 'Fallback to Desktop opengl headers.'
        c_options['use_opengl_es2'] = False


class KivyBuildExt(build_ext):

    def build_extensions(self):
        print 'Build configuration is:'
        for opt, value in c_options.iteritems():
            print ' *', opt, ' = ', repr(value)
        print 'Generate config.h'
        config_h = join(dirname(__file__), 'kivy', 'graphics', 'config.h')
        with open(config_h, 'w') as fd:
            fd.write('// Autogenerated file for Kivy C configuration\n')
            for k, v in c_options.iteritems():
                fd.write('#define __%s %d\n' % (k.upper(), int(v)))

        print 'Generate config.pxi'
        config_pxi = join(dirname(__file__), 'kivy', 'graphics', 'config.pxi')
        with open(config_pxi, 'w') as fd:
            fd.write('# Autogenerated file for Kivy Cython configuration\n')
            for k, v in c_options.iteritems():
                fd.write('DEF %s = %d\n' % (k.upper(), int(v)))

        build_ext.build_extensions(self)

cmdclass['build_ext'] = KivyBuildExt

# extension modules
ext_modules = []

# list all files to compile
pyx_files = []
pxd_files = []
kivy_libs_dir = realpath(join(kivy.kivy_base_dir, 'libs'))
for root, dirnames, filenames in walk(join(dirname(__file__), 'kivy')):
    # ignore lib directory
    if realpath(root).startswith(kivy_libs_dir):
        continue
    for filename in fnfilter(filenames, '*.pxd'):
        pxd_files.append(join(root, filename))
    for filename in fnfilter(filenames, '*.pyx'):
        pyx_files.append(join(root, filename))

# add cython core extension modules if cython is available

if True:
    libraries = ['m']
    include_dirs = []
    extra_link_args = []
    if platform == 'win32':
        libraries.append('opengl32')
    elif platform == 'darwin':
        # On OSX, it's not -lGL, but -framework OpenGL...
        extra_link_args = ['-framework', 'OpenGL']
    elif platform.startswith('freebsd'):
        include_dirs += ['/usr/local/include']
        extra_link_args += ['-L', '/usr/local/lib']
    else:
        libraries.append('GL')

    if c_options['use_glew']:
        if platform == 'win32':
            libraries.append('glew32')
        else:
            libraries.append('GLEW')

    def get_modulename_from_file(filename):
        pyx = '.'.join(filename.split('.')[:-1])
        pyxl = pyx.split(sep)
        while pyxl[0] != 'kivy':
            pyxl.pop(0)
        if pyxl[1] == 'kivy':
            pyxl.pop(0)
        return '.'.join(pyxl)

    class CythonExtension(Extension):

        def __init__(self, *args, **kwargs):
            # Small hack to only compile for x86_64 on OSX.
            # Is there a better way to do this?
            if platform == 'darwin':
                extra_args = ['-arch', 'x86_64']
                kwargs['extra_compile_args'] = extra_args + \
                    kwargs.get('extra_compile_args', [])
                kwargs['extra_link_args'] = extra_args + \
                    kwargs.get('extra_link_args', [])
            Extension.__init__(self, *args, **kwargs)
            self.pyrex_directives = {
                'profile': 'USE_PROFILE' in environ,
                'embedsignature': True}
            # XXX with pip, setuptools is imported before distutils, and change
            # our pyx to c, then, cythonize doesn't happen. So force again our
            # sources
            self.sources = args[1]

    # simple extensions
    for pyx in (x for x in pyx_files if not 'graphics' in x):
        pxd = [x for x in pxd_files if not 'graphics' in x]
        module_name = get_modulename_from_file(pyx)
        ext_modules.append(CythonExtension(module_name, [pyx] + pxd))

    # opengl aware modules
    for pyx in (x for x in pyx_files if 'graphics' in x):
        pxd = [x for x in pxd_files if 'graphics' in x]
        module_name = get_modulename_from_file(pyx)
        ext_modules.append(CythonExtension(
            module_name, [pyx] + pxd,
            libraries=libraries,
            include_dirs=include_dirs,
            extra_link_args=extra_link_args))


#setup datafiles to be included in the disytibution, liek examples...
#extracts all examples files except sandbox
data_file_prefix = 'share/kivy-'
examples = {}
examples_allowed_ext = ('readme', 'py', 'wav', 'png', 'jpg', 'svg', 'json',
                        'avi', 'gif', 'txt', 'ttf', 'obj', 'mtl', 'kv')
for root, subFolders, files in walk('examples'):
    if 'sandbox' in root:
        continue
    for file in files:
        ext = file.split('.')[-1].lower()
        if ext not in examples_allowed_ext:
            continue
        filename = join(root, file)
        directory = '%s%s' % (data_file_prefix, dirname(filename))
        if not directory in examples:
            examples[directory] = []
        examples[directory].append(filename)



# setup !
setup(
    name='Kivy',
    version=kivy.__version__,
    author='Kivy Crew',
    author_email='kivy-dev@googlegroups.com',
    url='http://kivy.org/',
    license='LGPL',
    description='A software library for rapid development of ' + \
                'hardware-accelerated multitouch applications.',
    ext_modules=ext_modules,
    cmdclass=cmdclass,
    packages=[
        'kivy',
        'kivy.core',
        'kivy.core.audio',
        'kivy.core.camera',
        'kivy.core.clipboard',
        'kivy.core.image',
        'kivy.core.gl',
        'kivy.core.spelling',
        'kivy.core.text',
        'kivy.core.video',
        'kivy.core.window',
        'kivy.ext',
        'kivy.graphics',
        'kivy.input',
        'kivy.input.postproc',
        'kivy.input.providers',
        'kivy.lib',
        'kivy.lib.osc',
        'kivy.modules',
        'kivy.network',
        'kivy.tools',
        'kivy.tools.packaging',
        'kivy.uix',
    ],
    package_dir={'kivy': 'kivy'},
    package_data={'kivy': [
        'data/*.kv',
        'data/*.json',
        'data/fonts/*.ttf',
        'data/images/*.png',
        'data/images/*.jpg',
        'data/images/*.gif',
        'data/images/*.atlas',
        'data/keyboards/*.json',
        'data/logo/*.png',
        'data/glsl/*.png',
        'data/glsl/*.vs',
        'data/glsl/*.fs',
        'tools/packaging/README.txt',
        'tools/packaging/win32/kivy.bat',
        'tools/packaging/win32/kivyenv.sh',
        'tools/packaging/win32/README.txt',
        'tools/packaging/osx/kivy.sh']},
    data_files=examples.items(),
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: MacOS X',
        'Environment :: Win32 (MS Windows)',
        'Environment :: X11 Applications',
        'Intended Audience :: Developers',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: Information Technology',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: GNU Library or Lesser '
        'General Public License (LGPL)',
        'Natural Language :: English',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX :: BSD :: FreeBSD',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Artistic Software',
        'Topic :: Games/Entertainment',
        'Topic :: Multimedia :: Graphics :: 3D Rendering',
        'Topic :: Multimedia :: Graphics :: Capture :: Digital Camera',
        'Topic :: Multimedia :: Graphics :: Presentation',
        'Topic :: Multimedia :: Graphics :: Viewers',
        'Topic :: Multimedia :: Sound/Audio :: Players :: MP3',
        'Topic :: Multimedia :: Video :: Display',
        'Topic :: Scientific/Engineering :: Human Machine Interfaces',
        'Topic :: Scientific/Engineering :: Visualization',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: User Interfaces'])

