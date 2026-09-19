# GCC 14+ Source Patches for pCloud Console Client

These patches fix actual compilation errors (not just warnings) when building
with GCC 14+. Apply them before running `make fs` in `lib/pclsync/`.

After applying these, you still need the CFLAGS relaxation in the Makefile
(see SKILL.md step 3) for the remaining type-mismatch warnings.

---

## 1. psynclib.c — Pointer dereferencing in thread callbacks

**Line ~2870** — `psync_async_delete_sync`:
```c
// BEFORE:
psync_syncid_t syncId = (psync_syncid_t*)ptr;
// AFTER:
psync_syncid_t syncId = *(psync_syncid_t*)ptr;
```

**Line ~2883** — `psync_async_ui_callback`:
```c
// BEFORE:
int eventId = (int*)ptr;
// AFTER:
int eventId = *(int*)ptr;
```

**Lines ~2897-2920** — `psync_delete_sync_by_folderid`:
The original code had uninitialized pointer + leaked allocation.
Replace the whole function body from `psync_syncid_t* syncId;` onward:
```c
// Remove syncIdT, allocate syncId directly, pass to thread
psync_syncid_t* syncId;

sqlRes = psync_sql_query_nolock(...);
...
syncId = psync_new(psync_syncid_t);
*syncId = row[0];
psync_sql_free_result(sqlRes);
psync_run_thread1("psync_async_sync_delete", psync_async_delete_sync, syncId);
```

---

## 2. pcallbacks.c — Pointer dereferencing

**Line ~438** — `psync_init_data_event`:
```c
// BEFORE:
data_event_fptr = (data_event_callback*)ptr;
// AFTER:
data_event_fptr = *(data_event_callback*)ptr;
```

---

## 3. pdiff.c — Wrong variable + type mismatch

**Line ~700** — `create_backend_event` call:
```c
// BEFORE (also use-after-free, res was freed on line 674):
res);
// AFTER:
&(char*){NULL});
```

---

## 4. ptimer.c — Extra argument

**Line ~167**:
```c
// BEFORE:
return psync_time(NULL);
// AFTER:
return psync_time();
```

---

## 5. pdownload.c — Extra argument

**Line ~442**:
```c
// BEFORE:
psync_sql_commit_transaction(sql);
// AFTER:
psync_sql_commit_transaction();
```

---

## 6. pp2p.c + pssl.c — Pointer-to-pointer for RSA decrypt

**pp2p.c line ~629**:
```c
// BEFORE:
psync_ssl_rsa_decrypt_symm_key_lock(psync_rsa_private, ekey)
// AFTER:
psync_ssl_rsa_decrypt_symm_key_lock(&psync_rsa_private, &ekey)
```

**pssl.c line ~69** — `psync_ssl_rsa_decrypt_symm_key_lock` body:
```c
// BEFORE:
sym_key = psync_ssl_rsa_decrypt_symmetric_key(rsa, enckey);
// AFTER:
sym_key = psync_ssl_rsa_decrypt_symmetric_key(*rsa, *enckey);
```

---

## 7. publiclinks.c — Missing forward declaration

Add before first usage (after includes):
```c
int process_bres(const char* cmd, binresult *bres, psync_socket *api, char **err);
```
Function is defined at line ~1478 but used starting at line ~717.

---

## 8. pdevice_monitor.c — Timer callback signature

**Line ~24**:
```c
// BEFORE:
void devmon_activity_timer_action(){
// AFTER (must match psync_timer_callback typedef):
void devmon_activity_timer_action(psync_timer_t timer, void *param){
```

---

## 9. pcloudcrypto.c — Extra arguments

**Line ~1693**:
```c
// BEFORE:
if (!crypto_keys_match(pub, priv))
// AFTER (function takes no args):
if (!crypto_keys_match())
```
