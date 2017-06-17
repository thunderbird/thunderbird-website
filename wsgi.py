import settings

def application(environ, start_response):
    if "Firefox" in environ["HTTP_USER_AGENT"]:
        content = 'text/plain'
    else:
        content = 'application/json'

    accept_language = environ.get('HTTP_ACCEPT_LANGUAGE', 'en-US')

    start_response('200 OK',
    [('Content-type', content ),
    ('Cache-Control', 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'),
    ('Pragma', 'no-cache'),
    ('Expires', '02 Jan 2010 00:00:00 GMT' )])

    print Request(environ).path_info_peek()
    print accept_language

    return


if __name__ == '__main__':
    #this runs when script is started directly from commandline
    try:
        #   create a simple WSGI server and run the application
        from wsgiref import simple_server
        print   "Running test   application -   point   your browser at http://localhost:8000/ ..."
        httpd   =   simple_server.WSGIServer(('',   8000), simple_server.WSGIRequestHandler)
        httpd.set_app(application)
        httpd.serve_forever()
    except ImportError:
        #wsgiref not installed, just output html to stdout
        for content in application({}, lambda status, headers: None):
            print content

