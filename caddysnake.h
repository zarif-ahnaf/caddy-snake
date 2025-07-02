// Copyright 2024 <Miguel Liezun>
#ifndef CADDYSNAKE_H_
#define CADDYSNAKE_H_

#include <stdint.h>
#include <stdlib.h>

void Py_init_and_release_gil(const char *);

typedef struct {
  // Capacity and length of the map work the same as in go slices.
  size_t length;
  size_t capacity;
  char **keys;
  char **values;
} MapKeyVal;
MapKeyVal *MapKeyVal_new(size_t);
void MapKeyVal_free(MapKeyVal *map);

// Shared Memory Communication Structures
#define SHM_MSG_SIZE (1 << 20)  // 1MB per message
#define SHM_QUEUE_SIZE 128      // Number of slots in each queue
#define MAX_WORKERS 16

typedef enum {
    MSG_TYPE_WSGI_REQUEST = 1,
    MSG_TYPE_WSGI_RESPONSE = 2,
    MSG_TYPE_ASGI_REQUEST = 3,
    MSG_TYPE_ASGI_RESPONSE = 4,
    MSG_TYPE_ASGI_EVENT = 5,
    MSG_TYPE_SHUTDOWN = 99
} MessageType;

typedef struct {
    size_t head;
    size_t tail;
    uint8_t data[SHM_QUEUE_SIZE][SHM_MSG_SIZE];
} spsc_queue_t;

typedef struct {
    MessageType type;
    uint64_t request_id;
    uint32_t worker_id;
    uint32_t data_size;
    char data[SHM_MSG_SIZE - sizeof(MessageType) - sizeof(uint64_t) - sizeof(uint32_t) - sizeof(uint32_t)];
} Message;

typedef struct {
    spsc_queue_t *request_queue;
    spsc_queue_t *response_queue;
    int shm_fd_req;
    int shm_fd_resp;
    pid_t worker_pid;
    uint32_t worker_id;
} WorkerContext;

typedef struct {
    uint32_t num_workers;
    WorkerContext workers[MAX_WORKERS];
    uint32_t next_worker;  // Round-robin counter
} WorkerPool;

// Worker Pool Management
WorkerPool* worker_pool_create(uint32_t num_workers, const char *module_name, 
                              const char *app_name, const char *working_dir, 
                              const char *venv_path, int is_asgi);
void worker_pool_destroy(WorkerPool *pool);
int worker_pool_send_request(WorkerPool *pool, Message *msg);
int worker_pool_receive_response(WorkerPool *pool, uint32_t worker_id, Message *msg);

// Message queue operations
int enqueue_message(spsc_queue_t *q, const Message *msg);
int dequeue_message(spsc_queue_t *q, Message *msg);

// Worker process functions  
void python_worker_main(uint32_t worker_id, const char *shm_req_name, 
                       const char *shm_resp_name, const char *module_name,
                       const char *app_name, const char *working_dir, 
                       const char *venv_path, int is_asgi);

// WSGI Protocol
typedef struct WsgiApp WsgiApp;
WsgiApp *WsgiApp_import(const char *, const char *, const char *, const char *);
void WsgiApp_handle_request(WsgiApp *, int64_t, MapKeyVal *, const char *,
                            size_t);
void WsgiApp_cleanup(WsgiApp *);

extern void wsgi_write_response(int64_t, int, MapKeyVal *, char *, size_t);

// ASGI 3.0 protocol

typedef struct AsgiApp AsgiApp;
typedef struct AsgiEvent AsgiEvent;
AsgiApp *AsgiApp_import(const char *, const char *, const char *, const char *);
uint8_t AsgiApp_lifespan_startup(AsgiApp *);
uint8_t AsgiApp_lifespan_shutdown(AsgiApp *);
void AsgiApp_handle_request(AsgiApp *, uint64_t, MapKeyVal *, MapKeyVal *,
                            const char *, int, const char *, int, const char *);
void AsgiEvent_set(AsgiEvent *, const char *, size_t, uint8_t, uint8_t);
void AsgiEvent_set_websocket(AsgiEvent *, const char *, size_t, uint8_t,
                             uint8_t);
void AsgiEvent_websocket_set_connected(AsgiEvent *);
void AsgiEvent_websocket_set_disconnected(AsgiEvent *);
void AsgiEvent_cleanup(AsgiEvent *);
void AsgiApp_cleanup(AsgiApp *);

extern uint8_t asgi_receive_start(uint64_t, AsgiEvent *);
extern void asgi_send_response(uint64_t, char *, size_t, uint8_t, AsgiEvent *);
extern void asgi_send_response_websocket(uint64_t, char *, size_t, uint8_t,
                                         AsgiEvent *);
extern void asgi_set_headers(uint64_t, int, MapKeyVal *, AsgiEvent *);
extern void asgi_cancel_request(uint64_t);
extern void asgi_cancel_request_websocket(uint64_t, char *, int);

#endif // CADDYSNAKE_H_
