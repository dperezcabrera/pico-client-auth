# Especificacion: Grupos en pico-auth

## Motivacion

Hoy cada herramienta (service-desk, task-board) define y gestiona sus propios
grupos de forma aislada. Service-desk tiene `SDG-*` con miembros, task-board
podria tener grupos de board, y cualquier herramienta futura repetiria el
patron.

Un grupo es un concepto de **identidad**: quienes son y a que pertenecen. Las
herramientas de dominio necesitan saber *a que grupo va este ticket* o *quien
puede ver este board*, pero no deberian ser duenas de la definicion del grupo
ni de sus miembros.

La separacion es limpia:

| Capa | Responsabilidad | Ejemplo |
|------|----------------|---------|
| pico-auth | Identidad del grupo: nombre, miembros, metadata | "El grupo Infra tiene a Alice, Bob y Carol" |
| service-desk | Reglas de dominio asociadas a un grupo | "Los tickets `incident/hardware` van al grupo Infra, SLA critico 15 min" |
| task-board | Permisos y ownership de boards | "El board Sprint-3 pertenece al grupo Dev" |

Cada herramienta solo almacena un `group_id` como referencia y define sus
propias reglas de negocio alrededor. No duplica miembros, no sincroniza nada.

## Estado actual

### pico-client-auth (este repo)

Es una **libreria cliente** que valida JWTs emitidos por un auth server
externo. No gestiona usuarios ni grupos — solo decodifica tokens.

```python
@dataclass(frozen=True)
class TokenClaims:
    sub: str        # user_id
    email: str
    role: str       # superadmin | org_admin | operator | viewer
    org_id: str
    jti: str
```

No existe aun un auth server propio (pico-auth-server). Los tokens los emite
un servicio externo configurado via `issuer`.

### service-desk

Gestiona grupos standalone con CRUD completo:

- `POST /api/groups` — crea grupo con nombre, descripcion, miembros
- `GET /api/groups/{id}` — devuelve grupo con sus tickets
- Los tickets referencian `group_id` para ruteo y asignacion
- Borrar un grupo con tickets activos falla (integridad referencial)

Los miembros son strings libres (no validados contra ningun directorio).

## Propuesta

### Fase 1: Modelo de grupos en pico-auth

Ampliar pico-client-auth (o crear pico-auth-server si se decide separar) con
un modelo de grupos que sea la fuente de verdad de identidad.

#### Entidad Group

```
Group:
  id: str           # auto-generado, ej. "grp-001"
  name: str         # nombre visible, ej. "Infrastructure Team"
  description: str
  org_id: str       # tenant — un grupo pertenece a una org
  members: [str]    # lista de user_id (sub del JWT)
  created_at: datetime
  updated_at: datetime
```

#### API (si hay auth server)

```
POST   /api/v1/groups              — crear grupo
GET    /api/v1/groups              — listar grupos (filtro por org_id)
GET    /api/v1/groups/{id}         — detalle del grupo con miembros
PUT    /api/v1/groups/{id}         — actualizar nombre, descripcion, miembros
DELETE /api/v1/groups/{id}         — eliminar grupo
POST   /api/v1/groups/{id}/members — anadir miembro
DELETE /api/v1/groups/{id}/members/{user_id} — quitar miembro
```

#### Claims en el JWT

Anadir `groups` al token para que las herramientas downstream puedan resolver
pertenencia sin hacer llamadas adicionales:

```python
@dataclass(frozen=True)
class TokenClaims:
    sub: str
    email: str
    role: str
    org_id: str
    jti: str
    groups: list[str]   # ["grp-001", "grp-002"]
```

Esto permite que service-desk sepa si el usuario actual pertenece al grupo
asignado a un ticket sin consultar pico-auth en cada request.

### Fase 2: Herramientas referencian grupos de auth

#### service-desk

Los grupos `SDG-*` dejan de ser entidades propias. En su lugar:

- `create_ticket` recibe un `group_id` que es un grupo de pico-auth
- La tabla de config de service-desk asocia tipo de ticket a grupo:

```yaml
service_desk:
  routing:
    incident/hardware: grp-infra
    incident/software: grp-dev
    service_request/access: grp-security
```

- El endpoint `GET /api/groups/{id}` de service-desk se convierte en un proxy
  que enriquece el grupo de auth con datos de dominio (tickets asignados, SLA
  activos, metricas)
- `POST /api/groups` desaparece de service-desk — los grupos se crean en
  pico-auth

#### task-board

- Un board puede tener un `group_id` opcional que define quien tiene acceso
- La verificacion de acceso usa el claim `groups` del JWT — sin llamada
  adicional

#### Plugin servicedesk

- `servicedesk.create_group` pasa a llamar a pico-auth en vez de service-desk
- `servicedesk.list_groups` idem
- Los skills de tickets siguen llamando a service-desk (dominio)

### Fase 3: Resolucion de miembros

Cuando una herramienta necesita listar miembros de un grupo (ej. para mostrar
"asignables" en un ticket), tiene dos caminos:

1. **JWT claims** — si el usuario actual esta haciendo la peticion y solo
   necesita saber si *el* pertenece al grupo, el claim `groups` basta.

2. **API call a pico-auth** — si necesita listar *todos* los miembros (ej. un
   dropdown de asignacion), hace `GET /api/v1/groups/{id}` a pico-auth.

No hay cache ni sync de miembros. La fuente de verdad es siempre pico-auth.

## Que NO hace pico-auth

- No conoce tipos de ticket, SLA, columnas de board, ni ninguna logica de
  dominio
- No rutea tickets ni gestiona transiciones
- No almacena preferencias de herramientas por grupo
- No replica datos de dominio

## Decisiones pendientes

1. **pico-client-auth vs pico-auth-server** — hoy este repo es una libreria
   cliente. Los grupos requieren persistencia y API propia. Opciones:
   - Crear un nuevo repo `pico-auth-server` con la API de grupos (y
     potencialmente emision de tokens propia)
   - Ampliar este repo para que tambien pueda actuar como server embebido
   - Delegar en el auth server externo existente y solo consumir

2. **Migracion de service-desk** — los grupos `SDG-*` existentes necesitan
   una migracion. Opciones:
   - Crear grupos equivalentes en pico-auth y reapuntar las referencias
   - Mantener compatibilidad temporal con ambos modelos
   - Romper compatibilidad (aceptable si no hay datos en produccion)

3. **Granularidad de permisos en grupos** — un miembro de grupo tiene acceso
   total o necesitamos roles dentro del grupo (admin, member, viewer)?
   Empezar con flat membership y anadir roles solo si aparece la necesidad.

4. **Limites** — maximo de miembros por grupo, maximo de grupos por org,
   maximo de grupos por usuario. Definir cuando haya datos reales.

## Orden de implementacion sugerido

1. Decidir pico-client-auth vs pico-auth-server
2. Implementar entidad Group + API CRUD
3. Anadir claim `groups` al JWT
4. Actualizar `TokenClaims` en pico-client-auth
5. Refactorizar service-desk para usar `group_id` de auth
6. Actualizar plugin servicedesk
7. Opcionalmente, anadir `group_id` a task-board
