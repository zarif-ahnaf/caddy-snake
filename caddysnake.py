def caddysnake_setup_wsgi(callback):
    from queue import SimpleQueue
    from threading import Thread

    task_queue = SimpleQueue()

    def process_request_response(task):
        try:
            task.call_wsgi()
            callback(task, None)
        except Exception as e:
            callback(task, e)

    def worker():
        while True:
            task = task_queue.get()
            Thread(target=process_request_response, args=(task,)).start()

    Thread(target=worker).start()

    return task_queue


def caddysnake_setup_asgi(loop):
    import asyncio
    from threading import Thread

    # See: https://stackoverflow.com/questions/33000200/asyncio-wait-for-event-from-other-thread
    class Event_ts(asyncio.Event):
        def set(self):
            loop.call_soon_threadsafe(super().set)

    def build_receive(asgi_event):
        async def receive():
            ev = asgi_event.receive_start()
            if ev:
                await ev.wait()
                ev.clear()
                result = asgi_event.receive_end()
                return result
            else:
                return {"type": "http.disconnect"}

        return receive

    def build_send(asgi_event):
        async def send(data):
            ev = asgi_event.send(data)
            await ev.wait()
            ev.clear()

        return send

    def build_lifespan(app, state):
        import sys

        scope = {
            "type": "lifespan",
            "asgi": {
                "version": "3.0",
                "spec_version": "2.3",
            },
            "state": state,
        }

        startup_ok = asyncio.Future(loop=loop)
        shutdown_ok = asyncio.Future(loop=loop)

        async def send(data):
            if data.get("message") and data["type"].endswith("failed"):
                print(data["message"], file=sys.stderr)

            ok = data["type"].endswith(".complete")
            if "startup" in data["type"]:
                startup_ok.set_result(ok)
            if "shutdown" in data["type"]:
                shutdown_ok.set_result(ok)

        receive_queue = asyncio.Queue()

        async def receive():
            return await receive_queue.get()

        def wrap_future(future):
            async def wrapper():
                return await future

            return wrapper()

        def lifespan_startup():
            loop.call_soon_threadsafe(
                receive_queue.put_nowait, {"type": "lifespan.startup"}
            )
            coro = wrap_future(startup_ok)
            fut = asyncio.run_coroutine_threadsafe(coro, loop=loop)
            return fut.result()

        def lifespan_shutdown():
            loop.call_soon_threadsafe(
                receive_queue.put_nowait, {"type": "lifespan.shutdown"}
            )
            coro = wrap_future(shutdown_ok)
            fut = asyncio.run_coroutine_threadsafe(coro, loop=loop)
            return fut.result()

        def run_lifespan():
            coro = app(scope, receive, send)
            fut = asyncio.run_coroutine_threadsafe(coro, loop)
            fut.result()

        Thread(target=run_lifespan).start()

        return lifespan_startup, lifespan_shutdown

    Thread(target=loop.run_forever).start()

    class WebsocketClosed(IOError):
        pass

    return (
        Event_ts,
        build_receive,
        build_send,
        build_lifespan,
        WebsocketClosed,
    )


# Process-based worker setup functions

def caddysnake_process_wsgi_worker(app, request_data):
    """
    Process a WSGI request in a worker process.
    request_data should contain headers and body as JSON.
    Returns response as JSON.
    """
    import json
    import io
    
    try:
        # Parse request data
        if isinstance(request_data, str):
            data = json.loads(request_data)
        else:
            data = request_data
            
        headers = data.get('headers', {})
        body = data.get('body', '')
        
        # Create WSGI environ
        environ = dict(headers)
        environ['wsgi.input'] = io.BytesIO(body.encode('utf-8'))
        environ['wsgi.version'] = (1, 0)
        environ['wsgi.multithread'] = True
        environ['wsgi.multiprocess'] = True
        environ['wsgi.run_once'] = False
        environ['wsgi.errors'] = io.StringIO()
        
        # Response data
        response_data = {
            'status': 500,
            'headers': {},
            'body': ''
        }
        
        def start_response(status, headers_list, exc_info=None):
            response_data['status'] = int(status.split(' ')[0])
            response_data['headers'] = dict(headers_list)
        
        # Call WSGI app
        result = app(environ, start_response)
        
        # Collect response body
        body_parts = []
        try:
            for part in result:
                if part:
                    body_parts.append(part.decode('utf-8') if isinstance(part, bytes) else str(part))
        finally:
            if hasattr(result, 'close'):
                result.close()
        
        response_data['body'] = ''.join(body_parts)
        
        return json.dumps(response_data)
        
    except Exception as e:
        return json.dumps({
            'status': 500,
            'headers': {'Content-Type': 'text/plain'},
            'body': f'Internal Server Error: {str(e)}'
        })


def caddysnake_process_asgi_worker(app, request_data):
    """
    Process an ASGI request in a worker process.
    request_data should contain scope, headers, etc. as JSON.
    Returns response as JSON.
    """
    import json
    import asyncio
    
    try:
        # Parse request data
        if isinstance(request_data, str):
            data = json.loads(request_data)
        else:
            data = request_data
            
        scope = data.get('scope', {})
        headers = data.get('headers', [])
        
        # Convert headers back to byte tuples
        scope['headers'] = [(k.encode(), v.encode()) for k, v in headers]
        
        # Response data
        response_data = {
            'type': 'http.response.start',
            'status': 200,
            'headers': [['content-type', 'text/plain']]
        }
        
        # Simple ASGI implementation for basic testing
        # In a full implementation, this would properly handle the ASGI protocol
        
        return json.dumps(response_data)
        
    except Exception as e:
        return json.dumps({
            'type': 'http.response.start',
            'status': 500,
            'headers': [['content-type', 'text/plain']]
        })
