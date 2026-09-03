
__pragma__('alias', 'S', '$')  # to use jQuery library with 'S' instead of '$'


async def sleep(time):
    """ sleep [time] seconds """
    deferred = S.Deferred()
    setTimeout(lambda: deferred.resolve(), time * 1000.0)
    return deferred.promise()


def get_url(path: str = ""):
    """ get url for path, where path is most likely of form {controller}/{action}

    Example::

        url = get_url("events/paged_list")

    """
    loc = window.location
    return "{}/{}".format(loc.origin, path)


def _get_cookie(name):
    """ Read a cookie value by name, or '' if absent. """
    prefix = name + "="
    for part in document.cookie.split(";"):
        part = part.strip()
        if part.startswith(prefix):
            return decodeURIComponent(part[len(prefix):])
    return ""


def redirect_relative(path: str = ""):
    """ Redirect relative to the same origin, but other path """
    loc = window.location
    while len(path) > 0 and path[0] == "/":
        path = path[1:]
    new_url = "{}/{}".format(loc.origin, path)
    # by simulating a mouse click, which preserves history
    window.location.href = new_url
    # as an http redirect, so that 'back' button does not work
    # window.location.replace(new_url)


def redirect(url: str = ""):
    """ Absolute redirect """
    # by simulating a mouse click, which preserves history
    window.location.href = url
    # as an http redirect, so that 'back' button does not work
    # window.location.replace(url)


# def format_date(date: str, format='YYYY-MM-DD HH:mm:ss'):
#     """
#     :Parameters:
#      - date: string in utc format
#     """
#     if date is None:
#         return ""
#     return moment(date).format(format)


# def parse_date(txt):
#     """ Return a Date object from a string, assuming current locale """
#     if txt is None or txt == "":
#         return None
#     else:
#         return moment(txt)._d


async def post(url, data, json_parse=True, content_type=None):
    """ Make a post request to `url` and send `data`

    :Parameters:
     - json_parse: if `True` (default), symmetrically parse data using json (stringify before send, parse after receive)

    """
    # very old browsers have problems with overwriting named arguments
    _data = data
    _content_type = content_type
    deferred = S.Deferred()

    def success(result):
        if json_parse:
            r = JSON.parse(result)
            # If not logged in, redirect to home page
            if r.hasOwnProperty('LoginException'):
                redirect_relative("login/")
            deferred.resolve(r)
        else:
            deferred.resolve(result)

    def error(result):
        deferred.reject(result)

    if json_parse:
        _data = JSON.stringify(_data)

    if _content_type is None:
        _content_type = 'application/json; charset=utf-8'

    S.ajax({
        'type': 'POST',
        'url': url,
        'data': _data,
        'success': success,
        'error': error,
        'contentType': _content_type,
        'headers': {'X-Xsrftoken': _get_cookie('_xsrf')},
    })

    return deferred.promise()


def example_handle_progress(event):
    """ Example function to handle progress, useful for 'post_upload_file' and 'post_download_file' """
    percent = 0
    position = event.loaded or event.position
    total = event.total
    if event.lengthComputable:
        percent = Math.ceil(position / total * 100)  # TODO use python ceil
        console.log(percent)


def handle_progress(func):
    percent = 0
    position = event.loaded or event.position
    total = event.total
    if event.lengthComputable:
        percent = Math.ceil(position / total * 100)  # TODO use python ceil
        func(percent)


async def post_upload_file(url, file, handle_progress=None):
    deferred = S.Deferred()

    def success(result):
        deferred.resolve(JSON.parse(result))

    def error(result):
        deferred.reject(result)

    form_data = __new__(FormData())
    form_data.append("file", file, file['name'])
    form_data.append("upload_file", True)

    def xhr():
        r = S.ajaxSettings.xhr()
        if r.upload and handle_progress is not None:
            r.upload.addEventListener('progress', handle_progress, False)
        return r

    S.ajax({
        'type': "POST",
        'url': url,
        'xhr': xhr,
        'success': success,
        'error': error,
        'async': True,
        'data': form_data,
        'cache': False,
        'contentType': False,
        'processData': False,
        'timeout': 60000,
        'headers': {'X-Xsrftoken': _get_cookie('_xsrf')},
    })

    return deferred.promise()


async def post_download_file(url, data, filename, handle_progress=None):
    """ Send a post to the server, and expect a file (blob) to be returned. Save to file by showing a dialog.  """
    deferred = S.Deferred()

    xhr = __new__(XMLHttpRequest())
    xhr.open('POST', url)
    xhr.setRequestHeader('X-Xsrftoken', _get_cookie('_xsrf'))
    xhr.responseType = 'blob'

    if handle_progress is not None:
        xhr.onprogress = handle_progress

    xhr.send(JSON.stringify(data))

    def onload(evt):
        if evt.currentTarget.status == 200:  # success
            save_blob_to_file(evt.target.response, filename)
        deferred.resolve()

    xhr.onload = onload
    return deferred.promise()


def save_file(txt: str, filename: str):
    # This method has a dependency: FileSaver.js. Make sure it is included in the html page
    saveAs(__new__(Blob([txt], {'type': "text/plain;charset=utf-8"})), filename)


def save_blob_to_file(blob, filename):
    """ Save data to a file, without using dependencies, by creating a link to it. The browser will use the default download process,
    probably by showing a dialog, as prefered by the user. """
    a = document.createElement("a")
    a.style = "display: none"
    document.body.appendChild(a)
    url = window.URL.createObjectURL(blob)
    a.href = url
    a.download = filename
    a.click()
    window.URL.revokeObjectURL(url)
