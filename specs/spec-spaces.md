# Especificacion: Espacios Remotos Compartidos

## Que hay hoy

Plugins de storage existentes:

| Plugin | Que hace |
|--------|----------|
| `integration.shared_storage` | Operaciones S3 crudas (list, upload, download, delete, mkdir) |
| `integration.sharepoint` | Idem via Microsoft Graph |
| `integration.gdrive` | Idem via Google Drive API |
| `integration.storage` | Router unificado: delega a un provider nombrado por account |

Estos plugins resuelven la **fontaneria**: como hablar con S3, como firmar
requests, como subir bytes. Pero no tienen ningun concepto de:

- Quien puede acceder a que
- Espacios con nombre e identidad
- Permisos diferenciados (leer, escribir, administrar)
- Links compartibles con acceso limitado

## Que falta

Un espacio remoto compartido no es un bucket ni un drive. Es un concepto
**de dominio** que dice: "este conjunto de recursos pertenece a este grupo
de personas, con estas reglas de acceso".

Los providers existentes son el *backend de almacenamiento*. Lo que falta es
el *backend de espacios* que gestione la capa de acceso y delegue el
almacenamiento real al provider configurado.

## Marco conceptual

Tres entidades. Nada mas.

### 1. Space (espacio)

Un contenedor logico con nombre, owner y un provider de storage detras.

```
Space:
  id: str               # auto, ej. "spc-001"
  name: str             # "Documentacion Proyecto X"
  description: str
  org_id: str           # tenant
  owner_id: str         # user_id o group_id que creo el espacio
  provider: str         # "disk" | "s3" | "sharepoint" | "gdrive"
  provider_root: str    # path raiz en el provider, ej. "/spaces/spc-001/"
  created_at: datetime
  updated_at: datetime
```

Un espacio es una proyeccion logica sobre un directorio del provider. No
inventa un filesystem — usa el que ya existe.

### 2. Grant (permiso)

Quien puede hacer que en un espacio (o en un recurso concreto dentro de el).

```
Grant:
  id: str
  space_id: str         # a que espacio aplica
  grantee_type: str     # "user" | "group"
  grantee_id: str       # user_id o group_id (de pico-auth)
  permission: str       # "read" | "write" | "admin"
  path: str             # "/" = todo el espacio, "/reports/" = solo esa carpeta
  created_at: datetime
  granted_by: str       # user_id que otorgo el permiso
```

Reglas:

- `read` — listar y descargar
- `write` — read + subir, crear carpetas, eliminar ficheros propios
- `admin` — write + gestionar grants + eliminar espacio
- Un grant con `path: "/"` aplica a todo el espacio
- Un grant con `path: "/informes/"` aplica solo a ese prefijo y sus hijos
- El owner del espacio tiene `admin` implicito (no necesita grant)
- Sin grant = sin acceso. Denegacion por defecto.

### 3. Link (enlace compartible)

Un token de acceso de lectura a un recurso concreto, con expiracion.

```
Link:
  id: str               # auto, ej. "lnk-a1b2c3"
  space_id: str
  path: str             # recurso concreto, ej. "/informes/q1-2026.pdf"
  token: str            # token opaco, criptograficamente aleatorio
  created_by: str       # user_id
  expires_at: datetime  # obligatorio, sin links eternos
  max_downloads: int    # 0 = ilimitado, >0 = limite
  download_count: int   # contador actual
  created_at: datetime
```

Un link genera una URL del tipo:

```
GET /api/v1/spaces/links/{token}/download
```

No requiere autenticacion. El token es el acceso. Expira por tiempo o por
numero de descargas.

## Principio de diseno: mismas primitivas, distinto ambito

El agente ya tiene herramientas para operar sobre su workspace local:

| Primitiva local | Que hace |
|----------------|----------|
| `read_file(path)` | Leer contenido de un fichero |
| `write_file(path, content)` | Escribir contenido a un fichero |
| `patch_file(path, old, new)` | Reemplazar texto en un fichero |
| `list_dir(path)` | Listar un directorio |
| `search_files(query, path)` | Buscar texto en ficheros |
| `share_file(path)` | Marcar un fichero para compartir con el usuario |

Un espacio remoto es una **extension del workspace** — no un servicio de
transferencia de ficheros. Las primitivas deben ser las mismas, con dos
operaciones adicionales para mover ficheros entre local y remoto:

| Primitiva remota | Equivalente local | Diferencia |
|-----------------|-------------------|------------|
| `spaces.read` | `read_file` | Devuelve contenido del fichero remoto |
| `spaces.write` | `write_file` | Escribe contenido directamente en remoto |
| `spaces.patch` | `patch_file` | Find-replace sobre fichero remoto |
| `spaces.list` | `list_dir` | Lista directorio remoto |
| `spaces.search` | `search_files` | Busca texto en ficheros remotos |
| `spaces.share` | `share_file` | Genera link compartible |
| `spaces.download` | — (nuevo) | Copia fichero remoto → workspace local |
| `spaces.upload` | — (nuevo) | Copia fichero workspace local → remoto |

El agente puede leer un fichero remoto sin descargarlo, editarlo sin
descargarlo, y buscar en ficheros remotos sin descargar nada. Download y
upload son solo para cuando necesita el fichero en su sandbox local (ej.
para procesarlo con codigo) o subir algo que genero localmente.

## Selector de espacios

Un usuario puede tener acceso a multiples espacios, igual que puede tener
varias cuentas de email. El agente necesita:

1. Saber que espacios tiene disponibles
2. Poder seleccionar uno para operar
3. Tener uno por defecto para no repetir `space_id` en cada llamada

### Modelo: igual que cuentas de email o storage accounts

```
# Email: multiples cuentas, una activa
email.list_accounts   → ["trabajo", "personal"]
email.send(account="trabajo", to=..., subject=...)

# Storage: multiples accounts, una default
storage.list(account="backups", path="/")
storage.accounts      → ["backups", "media", "docs"]

# Spaces: multiples espacios, uno activo
spaces.list_spaces    → ["infra", "docs", "marketing"]
spaces.read(space="infra", path="/config.yaml")
```

### Como funciona

**`spaces.list_spaces`** — devuelve todos los espacios accesibles para el
usuario actual (derivado del JWT: espacios propios + espacios con grant).
Es el punto de entrada. El agente lo llama para saber donde puede operar.

**`space` como parametro** — todas las skills de ficheros, grants y links
reciben un `space` (nombre o id). Si no se pasa, usa el espacio por
defecto configurado en el plugin.

**Espacio por defecto** — configurable en el plugin:

```yaml
# En la config del plugin integration.spaces
default_space: "infra"    # nombre o id del espacio por defecto
```

Si el usuario dice "lee /config.yaml", el agente usa el espacio por
defecto. Si dice "lee /config.yaml del espacio de marketing", el agente
pasa `space="marketing"`.

### Resolucion del parametro `space`

El plugin acepta nombre o id:

1. Si `space` parece un id (`spc-001`), se usa directamente
2. Si es un nombre (`infra`), el plugin busca en la lista de espacios
   accesibles el que coincida por nombre (case-insensitive)
3. Si no se pasa, se usa `default_space` de la config
4. Si no hay default ni parametro, error: "specify a space or set a default"

Esto permite al agente decir `spaces.read(space="infra", path="/x.yaml")`
en lugar de tener que descubrir el id primero.

## API

```
# -- Spaces
POST   /api/v1/spaces                              — crear espacio
GET    /api/v1/spaces                              — listar espacios accesibles
GET    /api/v1/spaces/{id}                         — detalle del espacio
PUT    /api/v1/spaces/{id}                         — actualizar nombre/descripcion
DELETE /api/v1/spaces/{id}                         — eliminar espacio (admin)

# -- Files: primitivas de workspace (operan sobre contenido)
GET    /api/v1/spaces/{id}/files/read?path=...      — leer contenido de un fichero
POST   /api/v1/spaces/{id}/files/write              — escribir contenido a un fichero
POST   /api/v1/spaces/{id}/files/patch              — find-replace sobre un fichero
GET    /api/v1/spaces/{id}/files/list?path=/         — listar directorio
GET    /api/v1/spaces/{id}/files/search?q=...&path=/ — buscar texto en ficheros
DELETE /api/v1/spaces/{id}/files?path=...            — eliminar fichero
POST   /api/v1/spaces/{id}/files/mkdir               — crear carpeta

# -- Files: transferencia (mueven ficheros entre local y remoto)
POST   /api/v1/spaces/{id}/files/upload             — subir fichero binario desde local
GET    /api/v1/spaces/{id}/files/download?path=...  — descargar fichero binario a local

# -- Grants
POST   /api/v1/spaces/{id}/grants                  — otorgar permiso
GET    /api/v1/spaces/{id}/grants                  — listar permisos
DELETE /api/v1/spaces/{id}/grants/{grant_id}       — revocar permiso

# -- Links
POST   /api/v1/spaces/{id}/links                   — crear link compartible
GET    /api/v1/spaces/{id}/links                   — listar links activos
DELETE /api/v1/spaces/{id}/links/{link_id}         — revocar link
GET    /api/v1/spaces/links/{token}/download        — descargar via link (sin auth)
```

## Flujo de autorizacion

Cada request a un espacio pasa por:

1. Extraer `user_id` y `groups` del JWT (via pico-client-auth)
2. Buscar grants del espacio que apliquen al usuario:
   - Grants directos (`grantee_type=user`, `grantee_id=user_id`)
   - Grants por grupo (`grantee_type=group`, `grantee_id` in `groups` del JWT)
   - Owner implicito (`space.owner_id == user_id`)
3. Filtrar por path: el grant debe cubrir el path del recurso solicitado
4. Verificar permiso minimo: `read` para listar/descargar, `write` para
   subir/borrar, `admin` para gestionar grants
5. Sin match → 403

No hay herencia compleja. Un grant a `/` cubre todo. Un grant a `/docs/`
cubre `/docs/informe.pdf` pero no `/images/logo.png`.

## Provider `disk` — almacenamiento local

Para desarrollo, tests y despliegues ligeros donde no hace falta cloud.
El provider `disk` almacena ficheros en un directorio local del servidor.

### Comportamiento

Mismo contrato que los providers cloud, pero contra el filesystem:

| Operacion | Implementacion |
|-----------|---------------|
| list | `os.scandir` sobre el directorio |
| upload | `shutil.copy` / write bytes |
| download | read bytes del fichero |
| delete | `os.remove` / `shutil.rmtree` |
| mkdir | `os.makedirs` |

### Estructura en disco

```
{storage_root}/
└── {space_id}/           # provider_root = "/{space_id}/"
    ├── informes/
    │   └── q1-2026.pdf
    └── imagenes/
        └── logo.png
```

El `storage_root` es configurable. Cada espacio es un subdirectorio. No hay
magia — es el filesystem del servidor.

### Config

```yaml
spaces:
  prefix: SPC
  default_provider: disk    # <- para dev/test
  host: 0.0.0.0
  port: 9300

storage:
  disk:
    root: /var/lib/pico-spaces/data    # produccion
    # root: /tmp/pico-spaces           # dev/test
    max_file_size_mb: 100
```

### Seguridad

- El `root` debe estar fuera del workspace del agente y fuera de `/` paths
  peligrosos
- Path traversal: validar que todas las rutas resueltas quedan dentro de
  `{root}/{space_id}/`. Canonicalizar con `Path.resolve()` y verificar que
  el resultado empieza con el prefijo esperado
- No exponer rutas absolutas del servidor en las respuestas — los paths que
  ve el usuario son siempre relativos al espacio

### Cuando usar cada provider

| Escenario | Provider | Por que |
|-----------|----------|---------|
| Dev local, tests E2E, CI | `disk` | Sin credenciales, sin red, rapido |
| Produccion single-server | `disk` | Simple, suficiente si hay backup |
| Produccion multi-servidor | `s3` | Almacenamiento compartido, durable |
| Integracion con Microsoft 365 | `sharepoint` | Ficheros ya estan ahi |
| Integracion con Google Workspace | `gdrive` | Idem |

### Tests E2E del spaces-backend

Con `disk` los tests E2E no necesitan mock de S3 ni contenedores MinIO.
El fixture crea un `tmp_path`, configura `disk.root` apuntando ahi, y todas
las operaciones de ficheros son reales contra el filesystem temporal de
pytest. El mismo patron que task-board y service-desk con SQLite `:memory:`.

```python
@pytest.fixture()
def container(tmp_path):
    config_file = tmp_path / "application.yaml"
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    config_file.write_text(f"""\
database:
  url: "sqlite+aiosqlite:///:memory:"

spaces:
  prefix: SPC
  default_provider: disk

storage:
  disk:
    root: "{storage_root}"
    max_file_size_mb: 10
""")
    config = configuration(YamlTreeSource(str(config_file)))
    c = init(modules=["spaces"], config=config)
    yield c
    c.shutdown()
```

## Relacion con lo existente

```
┌─────────────────────────────────────────────┐
│  pico-auth                                  │
│  users, groups, JWT con claims              │
└──────────────┬──────────────────────────────┘
               │ user_id, groups[]
               ▼
┌─────────────────────────────────────────────┐
│  spaces-backend (nuevo)                     │
│  Space + Grant + Link                       │
│  autoriza acceso, genera links              │
│  delega I/O al provider                     │
└──────────────┬──────────────────────────────┘
               │ storage.list / upload / download
               ▼
┌─────────────────────────────────────────────┐
│  storage provider (existente)               │
│  S3 / SharePoint / GDrive                   │
│  operaciones crudas sobre ficheros          │
└─────────────────────────────────────────────┘
```

El spaces-backend es una capa fina entre auth y storage. No reimplementa
el almacenamiento — lo delega. No reimplementa la identidad — la consume.

## Implementacion con infra pico

Un servicio pico-boot standalone, igual que task-board y service-desk:

```
spaces/
├── application.yaml
├── pyproject.toml
└── spaces/
    ├── __init__.py
    ├── __main__.py
    ├── main.py
    ├── config.py          # SpacesSettings (@configured)
    ├── errors.py          # SpaceError (status_code)
    ├── entities.py        # SQLAlchemy: SpaceEntity, GrantEntity, LinkEntity
    ├── models.py          # Pydantic: request/response
    ├── schema.py          # alembic / create_all
    ├── api/
    │   └── controllers.py # SpacesController (@controller)
    ├── services/
    │   ├── spaces_service.py    # logica de dominio
    │   └── spaces_repository.py # acceso a DB
    └── tests/
        ├── conftest.py
        └── test_e2e.py
```

Config:

```yaml
database:
  url: "sqlite+aiosqlite:///spaces.db"

spaces:
  prefix: SPC
  default_provider: disk        # disk para dev, s3/sharepoint/gdrive para prod
  link_expiry_max_days: 30
  link_token_length: 32
  max_spaces_per_org: 100
  host: 0.0.0.0
  port: 9300

storage:
  disk:
    root: /var/lib/pico-spaces/data
    max_file_size_mb: 100
  # s3:
  #   bucket: my-spaces-bucket
  #   region: eu-west-1
  #   api_key: "..."
  #   secret_key: "..."
  # sharepoint:
  #   tenant_id: "..."
  #   client_id: "..."
  #   client_secret: "..."
  #   site_id: "..."
```

El servicio implementa una interfaz `StorageBackend` que refleja las
primitivas del workspace local:

```python
class StorageBackend(ABC):
    """Contrato que todo provider de storage debe cumplir."""

    # -- Primitivas de contenido (equivalentes al workspace local)
    async def read(self, root: str, path: str) -> bytes
    async def write(self, root: str, path: str, content: bytes) -> None
    async def delete(self, root: str, path: str) -> None
    async def list(self, root: str, path: str) -> list[FileEntry]
    async def mkdir(self, root: str, path: str) -> None
    async def search(self, root: str, query: str, path: str) -> list[SearchMatch]
    async def exists(self, root: str, path: str) -> bool
```

`patch` no es del provider — lo resuelve el servicio: `read` → reemplazar →
`write`. Igual que `patch_file` local es una operacion compuesta.

Cada provider (disk, s3, sharepoint, gdrive) implementa esta interfaz. Al
crear un espacio se selecciona el provider y el backend resuelve la
implementacion concreta.

## Plugin integration.spaces

### Posicion en el ecosistema

El plugin sigue el mismo patron que `integration.taskboard` y
`integration.servicedesk`: un `GenericIntegrationPlugin` con HTTP wrappers
que conecta al spaces-backend via REST. Vive en
`pico_bot/plugins/builtin/servicedesk/` como builtin con trust level
`BUILTIN`.

### Relacion con los plugins de storage existentes

Los plugins de storage (`shared_storage`, `sharepoint`, `gdrive`, `storage`)
siguen existiendo. Son la fontaneria de I/O.

`integration.spaces` **no los reemplaza ni depende de ellos**. El
spaces-backend habla directamente con el provider de storage (S3, Graph,
etc.) usando sus propias credenciales. El plugin de spaces habla con el
spaces-backend via HTTP — no con S3.

```
agente
  → plugin integration.spaces (HTTP al spaces-backend)
    → spaces-backend (autoriza, resuelve path, delega I/O)
      → S3 / SharePoint / GDrive (storage real)
```

Si el usuario quiere operar sobre S3 crudo sin control de acceso (uso
interno, scripts, etc.), sigue usando `storage.*` o `shared_storage.*`
directamente. Los dos caminos coexisten.

### Manifest: plugin.yaml

```yaml
id: integration.spaces
name: Shared Spaces
version: 1.0.0
description: Manage shared remote spaces with access control, file operations, and shareable links.
plugin_type: integration
entry_module: spaces_plugin
entry_class: SpacesPlugin
permissions:
  - name: network.http
    description: Connect to spaces-backend REST API
    required: false
config_schema:
  type: object
  additionalProperties: false
  properties:
    enabled:
      type: boolean
      default: false
    base_url:
      type: string
      default: "http://localhost:9300"
    api_token:
      type: string
      default: ""
      x-secret: true
    default_space:
      type: string
      default: ""
      description: "Default space name or ID. Used when no space is specified in a skill call."
    security_events:
      type: object
      additionalProperties: false
      properties:
        enabled: {type: boolean, default: false}
        sink: {type: string, enum: [noop, file, http], default: file}
        file_path: {type: string, default: memory/security_events/integration.spaces.jsonl}
        http:
          type: object
          additionalProperties: true
          properties:
            endpoint: {type: string, default: ""}
            method: {type: string, default: POST}
            timeout_ms: {type: integer, minimum: 100, maximum: 10000, default: 1500}
            headers: {type: object, additionalProperties: {type: string}, default: {}}
          default: {endpoint: "", method: POST, timeout_ms: 1500, headers: {}}
      default:
        enabled: false
        sink: file
        file_path: memory/security_events/integration.spaces.jsonl
        http: {endpoint: "", method: POST, timeout_ms: 1500, headers: {}}
default_config:
  enabled: false
  base_url: "http://localhost:9300"
  api_token: ""
  default_space: ""           # nombre o id del espacio por defecto
  security_events:
    enabled: false
    sink: file
    file_path: memory/security_events/integration.spaces.jsonl
    http: {endpoint: "", method: POST, timeout_ms: 1500, headers: {}}
```

### Virtual skills

Organizadas en los mismos grupos que las primitivas locales del agente,
mas gestion de espacios y acceso.

```yaml
virtual_skills:
  # -- Spaces (gestion)
  - skill_id: spaces.list_spaces
    method: list_spaces
    description: List all spaces accessible to the current user.
    timeout_ms: 30000
    input_schema:
      type: object
      additionalProperties: true
      properties:
        max_results: {type: integer, default: 20}

  - skill_id: spaces.get_space
    method: get_space
    description: Get details of a specific space.
    timeout_ms: 30000
    input_schema:
      type: object
      additionalProperties: true
      required: [space]
      properties:
        space: {type: string, description: "Space name or ID. Uses default_space if omitted."}

  - skill_id: spaces.create_space
    method: create_space
    description: Create a new shared space backed by a storage provider.
    timeout_ms: 30000
    input_schema:
      type: object
      additionalProperties: true
      required: [name]
      properties:
        name: {type: string}
        description: {type: string}
        provider: {type: string, enum: [disk, s3, sharepoint, gdrive], default: disk}

  - skill_id: spaces.delete_space
    method: delete_space
    description: Delete a space and all its contents (requires admin permission).
    timeout_ms: 30000
    input_schema:
      type: object
      additionalProperties: true
      required: [space]
      properties:
        space: {type: string, description: "Space name or ID. Uses default_space if omitted."}

  # -- Workspace primitives (operan sobre contenido remoto, como las locales)
  - skill_id: spaces.read
    method: read_file
    description: Read the contents of a remote file and return it as text. Equivalent to local read_file.
    timeout_ms: 30000
    input_schema:
      type: object
      additionalProperties: true
      required: [path]
      properties:
        space: {type: string, description: "Space name or ID. Uses default_space if omitted."}
        path: {type: string}

  - skill_id: spaces.write
    method: write_file
    description: Write text content to a remote file. Creates parent directories if needed. Equivalent to local write_file.
    timeout_ms: 30000
    input_schema:
      type: object
      additionalProperties: true
      required: [path, content]
      properties:
        space: {type: string, description: "Space name or ID. Uses default_space if omitted."}
        path: {type: string}
        content: {type: string}

  - skill_id: spaces.patch
    method: patch_file
    description: Find and replace text in a remote file. The old_text must exist exactly. Equivalent to local patch_file.
    timeout_ms: 30000
    input_schema:
      type: object
      additionalProperties: true
      required: [path, old_text, new_text]
      properties:
        space: {type: string, description: "Space name or ID. Uses default_space if omitted."}
        path: {type: string}
        old_text: {type: string}
        new_text: {type: string}

  - skill_id: spaces.list
    method: list_dir
    description: List files and folders at a path in a space. Equivalent to local list_dir.
    timeout_ms: 30000
    input_schema:
      type: object
      additionalProperties: true
      required: [space]
      properties:
        space: {type: string, description: "Space name or ID. Uses default_space if omitted."}
        path: {type: string, default: "/"}
        max_results: {type: integer, default: 100}

  - skill_id: spaces.search
    method: search_files
    description: Search for text inside files in a space. Equivalent to local search_files.
    timeout_ms: 60000
    input_schema:
      type: object
      additionalProperties: true
      required: [query]
      properties:
        space: {type: string, description: "Space name or ID. Uses default_space if omitted."}
        query: {type: string, description: "Literal text to search for"}
        path: {type: string, default: "/", description: "Directory to search from"}
        max_results: {type: integer, default: 100}

  - skill_id: spaces.delete
    method: delete_file
    description: Delete a file or empty folder from a space.
    timeout_ms: 30000
    input_schema:
      type: object
      additionalProperties: true
      required: [path]
      properties:
        space: {type: string, description: "Space name or ID. Uses default_space if omitted."}
        path: {type: string}

  - skill_id: spaces.mkdir
    method: create_folder
    description: Create a folder in a space. Creates parent directories if needed.
    timeout_ms: 30000
    input_schema:
      type: object
      additionalProperties: true
      required: [path]
      properties:
        space: {type: string, description: "Space name or ID. Uses default_space if omitted."}
        path: {type: string}

  # -- Transfer (mover ficheros entre workspace local y espacio remoto)
  - skill_id: spaces.upload
    method: upload_file
    description: Copy a file from the local workspace to a remote space.
    allow_attachments: true
    max_attachments: 1
    timeout_ms: 120000
    input_schema:
      type: object
      additionalProperties: true
      required: [local_path, remote_path]
      properties:
        space: {type: string, description: "Space name or ID. Uses default_space if omitted."}
        local_path: {type: string, description: "Path in local workspace"}
        remote_path: {type: string, description: "Destination path in the space"}

  - skill_id: spaces.download
    method: download_file
    description: Copy a file from a remote space to the local workspace.
    timeout_ms: 120000
    input_schema:
      type: object
      additionalProperties: true
      required: [remote_path]
      properties:
        space: {type: string, description: "Space name or ID. Uses default_space if omitted."}
        remote_path: {type: string, description: "Source path in the space"}
        local_path: {type: string, description: "Destination in local workspace (optional, defaults to filename)"}

  # -- Access (grants)
  - skill_id: spaces.grant_access
    method: grant_access
    description: Grant read, write, or admin access to a user or group on a space.
    timeout_ms: 30000
    input_schema:
      type: object
      additionalProperties: true
      required: [grantee_id, permission]
      properties:
        space: {type: string, description: "Space name or ID. Uses default_space if omitted."}
        grantee_type: {type: string, enum: [user, group], default: user}
        grantee_id: {type: string, description: "user_id or group_id from pico-auth"}
        permission: {type: string, enum: [read, write, admin]}
        path: {type: string, default: "/", description: "Scope the grant to a path prefix"}

  - skill_id: spaces.revoke_access
    method: revoke_access
    description: Revoke a previously granted access.
    timeout_ms: 30000
    input_schema:
      type: object
      additionalProperties: true
      required: [grant_id]
      properties:
        space: {type: string, description: "Space name or ID. Uses default_space if omitted."}
        grant_id: {type: string}

  - skill_id: spaces.list_grants
    method: list_grants
    description: List all access grants on a space.
    timeout_ms: 30000
    input_schema:
      type: object
      additionalProperties: true
      required: [space]
      properties:
        space: {type: string, description: "Space name or ID. Uses default_space if omitted."}

  # -- Sharing (links)
  - skill_id: spaces.share
    method: create_link
    description: Generate a shareable read-only link for a file, with expiration. Equivalent to local share_file.
    timeout_ms: 30000
    input_schema:
      type: object
      additionalProperties: true
      required: [path]
      properties:
        space: {type: string, description: "Space name or ID. Uses default_space if omitted."}
        path: {type: string, description: "File path within the space"}
        expires_in_hours: {type: integer, default: 168, description: "Link expiry (default 7 days)"}
        max_downloads: {type: integer, default: 0, description: "0 = unlimited"}

  - skill_id: spaces.list_links
    method: list_links
    description: List active shareable links on a space.
    timeout_ms: 30000
    input_schema:
      type: object
      additionalProperties: true
      required: [space]
      properties:
        space: {type: string, description: "Space name or ID. Uses default_space if omitted."}

  - skill_id: spaces.revoke_link
    method: revoke_link
    description: Revoke a shareable link.
    timeout_ms: 30000
    input_schema:
      type: object
      additionalProperties: true
      required: [space_id, link_id]
      properties:
        space: {type: string, description: "Space name or ID. Uses default_space if omitted."}
        link_id: {type: string}
```

### Correspondencia local ↔ remoto

```
Workspace local              Espacio remoto
─────────────────            ──────────────────
read_file(path)         →    spaces.read(space_id, path)
write_file(path, text)  →    spaces.write(space_id, path, content)
patch_file(path, o, n)  →    spaces.patch(space_id, path, old, new)
list_dir(path)          →    spaces.list(space_id, path)
search_files(q, path)   →    spaces.search(space_id, query, path)
share_file(path)        →    spaces.share(space_id, path, expires)
—                       →    spaces.upload(space_id, local, remote)
—                       →    spaces.download(space_id, remote, local)
```

El agente usa las mismas primitivas mentales para local y remoto. La unica
diferencia es que las remotas llevan un `space_id` delante.

### Que puede hacer el agente

Con estas skills, el agente puede ejecutar flujos completos en lenguaje
natural:

- "Lee el fichero /config/settings.yaml del espacio de infra"
- "Cambia el valor de `timeout` de 30 a 60 en ese fichero"
- "Busca donde se usa `DB_PASSWORD` en el espacio de documentacion"
- "Crea un fichero /informes/resumen.md con este contenido..."
- "Descarga el CSV de metricas a mi workspace para procesarlo con pandas"
- "Sube el grafico que genere al espacio de infra en /informes/"
- "Da acceso de lectura a marketing sobre /informes/"
- "Genera un link al informe Q1 que expire en 3 dias"
- "Quien tiene acceso al espacio de desarrollo?"

### Marketplace

El plugin se distribuye como **builtin** (empaquetado con pico-bot), igual
que taskboard y servicedesk. No va al marketplace externo inicialmente.

Razon: depende de un spaces-backend que hay que desplegar. No tiene sentido
instalarlo desde marketplace si no hay backend detras. Es un plugin de
infraestructura propia, no un conector generico.

Si en el futuro el spaces-backend se ofrece como SaaS, el plugin pasaria a
marketplace con trust level `VERIFIED`, y el `base_url` apuntaria al
endpoint cloud en lugar de `localhost:9300`.

```
# Builtin (ahora)
pico_bot/plugins/builtin/spaces/
├── plugin.yaml
└── src/
    └── spaces_plugin.py

# Marketplace (futuro, si aplica)
registry → integration.spaces v1.0.0
  trust_level: VERIFIED
  preapproved: true (en config del tenant)
  install: POST /api/v1/plugins/market/integration.spaces/install
```

La transicion de builtin a marketplace es transparente: mismo plugin.yaml,
mismo codigo, solo cambia donde se descubre.

## Lo que NO es esto

- No es un filesystem distribuido
- No es un gestor de versiones (no hay historial de ficheros)
- No reemplaza los providers de storage — los usa
- No gestiona identidad — la consume de pico-auth
- No tiene logica de dominio de tickets ni boards — es solo espacios

## Decisiones pendientes

1. **Donde vive el servicio** — repo propio (`spaces/`) como task-board y
   service-desk, o dentro de pico-bot. Recomendacion: repo propio, misma
   estructura que los otros.

2. **Storage directo vs via plugin** — el spaces-backend puede hablar
   directamente con S3 (usando el mismo codigo que SharedStoragePlugin)
   o delegando via HTTP al plugin ya activado. Directo es mas simple y
   evita una capa de indirecion innecesaria.

3. **Links: token en URL vs header** — para links compartibles el token
   debe ir en la URL (para que sea un link pegable). Implicacion: los
   tokens de link deben ser criptograficamente fuertes (secrets.token_urlsafe)
   y tener expiracion corta.

4. **Quota** — limites de almacenamiento por espacio u org. No implementar
   hasta que haya necesidad real.

5. **Notificaciones** — avisar cuando alguien comparte un espacio o genera
   un link. Fuera de scope inicial.
