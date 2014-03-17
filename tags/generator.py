import os
import sys
import time
import posixpath
import urllib
import threading

from BaseHTTPServer import HTTPServer
from SimpleHTTPServer import SimpleHTTPRequestHandler

import tags
import utils
import templatelang

def build_file(filename, outfilename, root=u'.', create_dir=True):
    filepath = os.path.join(root, filename)
    with utils.open_file(filepath) as infile:
        try:
            output = tags.render(infile.read(), filename=filename, rootdir=root)
        except templatelang.ParseBaseException as e:
            utils.print_parse_exception(e, filename)
            return

    with utils.open_file(outfilename, "w", create_dir=create_dir) as outfile:
        outfile.write(output)


def build_files(root=u'.', dest=u'_site', pattern=u'**/*.html', 
                exclude=u'_*/**', watch=False, force=False):
    try:
        os.stat(os.path.join(root, 'index.html'))
    except OSError:
        if not force:
            msg = "Oops, we can't find an index.html in the source folder.\n"+\
                  "If you want to build this folder anyway, use the --force\n"+\
                  "option."
            print(msg)
            sys.exit(1)

    print("Buliding site from '{0}' into '{1}'".format(root, dest))

    exclude = exclude or os.path.join(dest, u'**')
    for filename in utils.walk_folder(root or '.'):
        included = utils.matches_pattern(pattern, filename)
        excluded = utils.matches_pattern(exclude, filename)
        destfile = os.path.join(dest, filename)
        if included and not excluded: 
            build_file(filename, destfile, root=root)
        elif not excluded:
            filepath = os.path.join(root, filename)
            destpath = os.path.join(dest, filename)
            utils.copy_file(filepath, destpath)

    if watch:
        observer = _watch(root=root,
                          dest=dest,
                          pattern=pattern,
                          exclude=exclude)
        if not observer:
            return
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()


def _watch(root=u'.', dest=u'_site', pattern=u'**/*.html', exclude=u'_*/**'):

    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        msg = "The build --watch feature requires watchdog. \n"\
            + "Please install it with 'easy_install watchdog'."
        print(msg)
        return None

    class handler(FileSystemEventHandler):
        def on_any_event(self, event):
            exclude_path = os.path.join(os.getcwd(), exclude)
            if not utils.matches_pattern(exclude_path, event.src_path):
                build_files(root=root,
                            dest=dest,
                            pattern=pattern,
                            exclude=exclude)

    observer = Observer()
    observer.schedule(handler(), root, recursive=True)
    observer.start()

    print("Watching '{0}' ...".format(root))

    return observer


def serve_files(root=u'.', dest=u'_site', pattern=u'**/*.html', 
                exclude=u'_*/**', watch=False, port=8000, force=False):

    # setup server

    class RequestHandler(SimpleHTTPRequestHandler):
        
        def translate_path(self, path):
            root = os.path.join(os.getcwd(), dest)

            # normalize path and prepend root directory
            path = path.split('?',1)[0]
            path = path.split('#',1)[0]
            path = posixpath.normpath(urllib.unquote(path))
            words = path.split('/')
            words = filter(None, words)
            
            path = root
            for word in words:
                drive, word = os.path.splitdrive(word)
                head, word = os.path.split(word)
                if word in (os.curdir, os.pardir):
                    continue
                path = os.path.join(path, word)

            return path

    class StoppableHTTPServer(HTTPServer):

        def serve_until_shutdown(self):
            self._stopped = False
            while not self._stopped:
                try:
                    httpd.handle_request()
                except:
                    self._stopped=True
                    self.server_close()


        def shutdown(self):
            self._stopped = True            
            self.server_close()

    server_address = ('', port)
    httpd = StoppableHTTPServer(server_address, RequestHandler)
    server_thread = threading.Thread(
        target=httpd.serve_until_shutdown)
    server_thread.daemon = True
    server_thread.start()

    print("HTTP server started on port {0}".format(server_address[1]))

    # build files

    build_files(root=root,
                dest=dest,
                pattern=pattern,
                exclude=exclude,
                force=force)

    # watch files while server running

    if watch:
        observer = _watch(root=root,
                          dest=dest,
                          pattern=pattern,
                          exclude=exclude)
        if not observer:
            return
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            httpd.shutdown()
        observer.join()

    else:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            httpd.shutdown()

