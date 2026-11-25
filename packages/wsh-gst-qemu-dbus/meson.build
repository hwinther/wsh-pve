# The qemudbus GStreamer plugin (qemudbussrc, qemudbusaudiosrc) and the input bridge
# qemu-dbus-input. debian/rules passes the package version as -Dpackage_version.
project('wsh-gst-qemu-dbus', 'c',
  version : '0',
  license : 'GPL-3.0-only',
  meson_version : '>= 1.1',
  default_options : ['warning_level=2', 'c_std=gnu11', 'buildtype=release'])

gst_req = '>= 1.22'
glib_dep = dependency('glib-2.0', version : '>= 2.74')
gio_dep = dependency('gio-2.0')
gio_unix_dep = dependency('gio-unix-2.0')
gst_dep = dependency('gstreamer-1.0', version : gst_req)
gstbase_dep = dependency('gstreamer-base-1.0', version : gst_req)
gstvideo_dep = dependency('gstreamer-video-1.0', version : gst_req)
gstaudio_dep = dependency('gstreamer-audio-1.0', version : gst_req)

cdata = configuration_data()
cdata.set_quoted('PACKAGE', 'wsh-gst-qemu-dbus')
cdata.set_quoted('PACKAGE_VERSION', get_option('package_version'))
cdata.set_quoted('GST_PACKAGE_NAME', 'wsh-gst-qemu-dbus')
cdata.set_quoted('GST_PACKAGE_ORIGIN', 'https://github.com/hwinther/wsh-pve')
configure_file(output : 'config.h', configuration : cdata)
add_project_arguments('-DHAVE_CONFIG_H', '-Wno-unused-parameter',
  '-Wno-missing-field-initializers', language : 'c')

plugins_dir = gst_dep.get_variable('pluginsdir')

shared_library('gstqemudbus',
  'src/plugin.c', 'src/gstqemudbussrc.c', 'src/gstqemudbusaudiosrc.c', 'src/qemudbus.c',
  dependencies : [gst_dep, gstbase_dep, gstvideo_dep, gstaudio_dep, gio_dep, gio_unix_dep],
  gnu_symbol_visibility : 'hidden',
  install : true,
  install_dir : plugins_dir)

executable('qemu-dbus-input',
  'src/qemu-dbus-input.c', 'src/qemudbus.c',
  dependencies : [glib_dep, gio_dep, gio_unix_dep],
  install : true)
