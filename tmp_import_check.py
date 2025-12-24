import importlib.util
spec = importlib.util.spec_from_file_location('tw','src/gui/timeline_viewer_window.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print('Loaded', getattr(mod, 'TimelineViewerWindow', None))
