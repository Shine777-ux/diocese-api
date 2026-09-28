from fastapi import FastAPI, HTTPException, Query, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from fastapi.concurrency import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import uuid
import jwt
from datetime import datetime, timedelta

SECRET_KEY = "super-secret-key-change-me"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

from database import (
    init_db,
    db_get_stats,
    db_get_dioceses,
    db_get_diocese,
    db_create_diocese,
    db_update_diocese,
    db_delete_diocese,
    db_get_deaneries,
    db_get_deanery,
    db_create_deanery,
    db_update_deanery,
    db_delete_deanery,
    db_get_parishes,
    db_get_parish,
    db_create_parish,
    db_update_parish,
    db_delete_parish,
    db_get_families,
    db_get_family,
    db_create_family,
    db_update_family,
    db_delete_family,
    db_get_members,
    db_get_member,
    db_create_member,
    db_update_member,
    db_delete_member,
    db_create_user,
    db_update_user,
    db_authenticate_user,
    db_get_users,
    get_user_scope,
    get_db_connection,
    db_get_permissions,
    db_save_permissions,
    db_get_family_relations,
    db_get_member_family_relations,
    db_add_family_relation,
    db_delete_family_relation,
    db_create_ward,
    db_get_wards_by_parish,
    db_update_ward,
    db_delete_ward,
    db_create_group,
    db_get_groups_by_parish,
    db_update_group,
    db_delete_group,
    db_add_member_group,
    db_remove_member_group,
    db_get_bootstrap_data,
    db_get_events,
    db_get_event,
    db_create_event,
    db_update_event,
    db_delete_event,
    db_get_circulars,
    db_get_circular,
    db_create_circular,
    db_delete_circular,
    db_get_contributions,
    db_get_contribution,
    db_create_contribution,
    db_delete_contribution,
    db_get_contributions_summary,
    db_get_commissions,
    db_get_commission,
    db_get_programs,
    db_get_program,
    db_create_program,
    db_update_program,
    db_delete_program,
    db_get_program_participants,
    db_get_participant,
    db_register_participant,
    db_update_participant,
    db_delete_participant
)

from reports_certificates import (
    generate_sacramental_certificate,
    generate_contribution_receipt,
    generate_competition_certificate,
    export_members_to_excel,
    export_members_to_csv,
    export_contributions_to_excel
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Warning: Database initialization failed during startup: {e}")
        print("Please check your database credentials (MYSQL_HOST, MYSQL_PORT, etc.)")
    yield

app = FastAPI(
    title="Diocese ERP API",
    lifespan=lifespan
)

# Enable CORS for frontend local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_msg = str(exc)
    if "Can't connect to MySQL" in error_msg or "OperationalError" in str(type(exc)):
        detail = "Database connection failed: The configured MySQL host is unreachable. Please verify your Aiven or MySQL database service and Render environment variables."
    else:
        detail = f"Server error: {error_msg}"
    return JSONResponse(
        status_code=500,
        content={"detail": detail},
        headers={"Access-Control-Allow-Origin": "*"}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={"Access-Control-Allow-Origin": "*"}
    )

@app.get("/")
def root():
    return {"status": "ok", "service": "Diocese ERP API"}

@app.get("/api/health")
def health_check():
    db_status = "ok"
    try:
        conn = get_db_connection()
        conn.close()
    except Exception as e:
        db_status = f"error: {str(e)}"
    return {"service": "ok", "database": db_status}

# --- Pydantic Models for Input Validation ---

class DioceseModel(BaseModel):
    name: str
    bishop: Optional[str] = ""
    founded: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    address: Optional[str] = ""

class DeaneryModel(BaseModel):
    diocese_id: int
    name: str
    dean: Optional[str] = ""
    description: Optional[str] = ""

class ParishModel(BaseModel):
    deanery_id: int
    diocese_id: int
    name: str
    pastor: Optional[str] = ""
    assistant_pastor: Optional[str] = ""
    address: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""

class WardModel(BaseModel):
    parish_id: int
    name: str
    description: Optional[str] = ""

class GroupModel(BaseModel):
    parish_id: int
    name: str
    description: Optional[str] = ""

class MemberGroupModel(BaseModel):
    group_id: int
    role: Optional[str] = "Member"

class FamilyModel(BaseModel):
    parish_id: int
    ward_id: Optional[int] = None
    name: str
    address: Optional[str] = ""
    phone: Optional[str] = ""

class FamilyRelationModel(BaseModel):
    family1_id: int
    family2_id: int
    member_id: Optional[int] = None
    relationship_type: str
    notes: Optional[str] = ""
    transfer_member: Optional[bool] = False

class MemberModel(BaseModel):
    parish_id: Optional[int] = None
    family_id: Optional[int] = None
    first_name: str
    last_name: str
    gender: Optional[str] = "Male"
    dob: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    address: Optional[str] = ""
    role: Optional[str] = "Laity"
    avatar_url: Optional[str] = None
    
    # Sacraments
    baptism_received: Optional[bool] = False
    baptism_date: Optional[str] = None
    baptism_parish: Optional[str] = None
    
    communion_received: Optional[bool] = False
    communion_date: Optional[str] = None
    communion_parish: Optional[str] = None
    
    confirmation_received: Optional[bool] = False
    confirmation_date: Optional[str] = None
    confirmation_parish: Optional[str] = None
    
    marriage_received: Optional[bool] = False
    marriage_date: Optional[str] = None
    marriage_parish: Optional[str] = None
    
    holy_orders_received: Optional[bool] = False
    holy_orders_date: Optional[str] = None
    holy_orders_parish: Optional[str] = None

class EventModel(BaseModel):
    parish_id: Optional[int] = None
    diocese_id: Optional[int] = None
    title: str
    description: Optional[str] = ""
    event_type: Optional[str] = "Mass"
    start_time: str
    end_time: Optional[str] = None
    location: Optional[str] = None

class CircularModel(BaseModel):
    diocese_id: Optional[int] = None
    deanery_id: Optional[int] = None
    parish_id: Optional[int] = None
    title: str
    content: str
    priority: Optional[str] = "Normal"
    author: Optional[str] = "Chancery Office"
    publish_date: Optional[str] = None

class ContributionModel(BaseModel):
    parish_id: int
    family_id: Optional[int] = None
    member_id: Optional[int] = None
    category: str
    amount: float
    payment_method: Optional[str] = "Cash"
    reference_no: Optional[str] = None
    payment_date: Optional[str] = None
    notes: Optional[str] = None
    recorded_by: Optional[str] = None

class UserRegisterModel(BaseModel):
    username: str
    password: str
    role: Optional[str] = "Admin"
    avatar_url: Optional[str] = None
    deanery_id: Optional[int] = None
    parish_id: Optional[int] = None

class UserUpdateModel(BaseModel):
    role: Optional[str] = None
    avatar_url: Optional[str] = None
    deanery_id: Optional[int] = None
    parish_id: Optional[int] = None
    password: Optional[str] = None

class UserLoginModel(BaseModel):
    username: str
    password: str

class ProgramModel(BaseModel):
    commission_id: int
    diocese_id: Optional[int] = None
    deanery_id: Optional[int] = None
    parish_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    type: Optional[str] = "Program"
    target_audience: Optional[str] = "All"
    start_date: str
    end_date: Optional[str] = None
    venue: Optional[str] = None
    registration_deadline: Optional[str] = None
    eligibility: Optional[str] = None
    guidelines: Optional[str] = None
    max_participants: Optional[int] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    status: Optional[str] = "Upcoming"
    banner_url: Optional[str] = None

class ParticipantRegisterModel(BaseModel):
    parish_id: int
    member_id: Optional[int] = None
    participant_name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    team_name: Optional[str] = None
    category: Optional[str] = "General"
    status: Optional[str] = "Registered"

class ParticipantUpdateModel(BaseModel):
    participant_name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    team_name: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    score: Optional[float] = None
    rank: Optional[str] = None
    certificate_issued: Optional[int] = None

# --- Authentication Helpers ---


def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")
    
    token = authorization.split(" ")[1]
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
        
    username = payload.get("sub")
    role = payload.get("role")
    uid = payload.get("uid")
    deanery_id = payload.get("deanery_id")
    parish_id = payload.get("parish_id")

    # Fast-path: If role and uid are present with deanery/parish (or superuser), avoid extra DB query
    if role and uid is not None and (deanery_id is not None or parish_id is not None or (role and role.lower() in ("admin", "administrator", "bishop"))):
        return {"id": uid, "username": username, "role": role, "deanery_id": deanery_id, "parish_id": parish_id}

    # Fetch from DB for fresh user info with deanery_id and parish_id
    conn = get_db_connection()
    user = conn.execute("SELECT id, username, role, avatar_url, deanery_id, parish_id FROM users WHERE username = ? OR id = ?", (username, uid)).fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return dict(user)

def check_permission(page: str, action: str):
    def dependency(current_user: dict = Depends(get_current_user)):
        user_role = current_user["role"]
        
        # Superuser access check
        if user_role.lower() in ("admin", "administrator"):
            return current_user
            
        # Use in-memory cached permissions instead of querying DB on every check
        perms = db_get_permissions(user_role)
        target_page = page.lower()
        col = f"can_{action}"
        row = next((p for p in perms if p.get("page", "").lower() == target_page), None)
        
        if not row or row.get(col) != 1:
            raise HTTPException(
                status_code=403, 
                detail=f"Permission denied. Role '{user_role}' does not have '{action}' permission on page '{page}'."
            )
        return current_user
    return dependency

def require_admin(current_user: dict = Depends(check_permission("Users", "view"))):
    return current_user

# --- Endpoints ---

# Permissions Pydantic Input Models
class PagePermissionModel(BaseModel):
    page: str
    can_create: int
    can_view: int
    can_edit: int
    can_delete: int
    can_export: int
    can_print: int
    can_send: int

class UpdatePermissionsModel(BaseModel):
    role: str
    permissions: List[PagePermissionModel]

@app.get("/api/permissions")
def get_permissions(role: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    return db_get_permissions(role)

@app.post("/api/permissions")
def save_role_permissions(payload: UpdatePermissionsModel, current_user: dict = Depends(check_permission("Permissions", "edit"))):
    try:
        db_save_permissions(payload.role, [p.dict() for p in payload.permissions])
        return {"message": "Permissions updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Dashboard Stats
@app.get("/api/stats")
def get_stats(current_user: dict = Depends(get_current_user)):
    try:
        scope = get_user_scope(current_user)
        return db_get_stats(allowed_parish_ids=scope["allowed_parish_ids"] if not scope["is_all"] else None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Coordinated Bootstrap Endpoint (dioceses, deaneries, parishes, members in 1 single connection/trip)
@app.get("/api/bootstrap")
def get_bootstrap_data_endpoint(current_user: dict = Depends(get_current_user)):
    try:
        scope = get_user_scope(current_user)
        return db_get_bootstrap_data(
            allowed_parish_ids=scope["allowed_parish_ids"] if not scope["is_all"] else None,
            deanery_id=scope["deanery_id"] if not scope["is_all"] else None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Dioceses CRUD
@app.get("/api/dioceses")
def get_dioceses(current_user: dict = Depends(check_permission("Diocese", "view"))):
    return db_get_dioceses()

@app.get("/api/dioceses/{diocese_id}")
def get_diocese(diocese_id: int, current_user: dict = Depends(check_permission("Diocese", "view"))):
    res = db_get_diocese(diocese_id)
    if not res:
        raise HTTPException(status_code=404, detail="Diocese not found")
    return res

@app.post("/api/dioceses")
def create_diocese(diocese: DioceseModel, current_user: dict = Depends(check_permission("Diocese", "create"))):
    d_id = db_create_diocese(diocese.dict())
    return {"id": d_id, "message": "Diocese created successfully"}

@app.put("/api/dioceses/{diocese_id}")
def update_diocese(diocese_id: int, diocese: DioceseModel, current_user: dict = Depends(check_permission("Diocese", "edit"))):
    res = db_get_diocese(diocese_id)
    if not res:
        raise HTTPException(status_code=404, detail="Diocese not found")
    db_update_diocese(diocese_id, diocese.dict())
    return {"message": "Diocese updated successfully"}

@app.delete("/api/dioceses/{diocese_id}")
def delete_diocese(diocese_id: int, current_user: dict = Depends(check_permission("Diocese", "delete"))):
    res = db_get_diocese(diocese_id)
    if not res:
        raise HTTPException(status_code=404, detail="Diocese not found")
    db_delete_diocese(diocese_id)
    return {"message": "Diocese deleted successfully"}

# Deaneries CRUD
@app.get("/api/deaneries")
def get_deaneries(diocese_id: Optional[int] = None, current_user: dict = Depends(check_permission("Deaneries", "view"))):
    scope = get_user_scope(current_user)
    if not scope["is_all"]:
        d_id = scope.get("deanery_id")
        if d_id:
            d = db_get_deanery(d_id)
            return [d] if d else []
        return []
    return db_get_deaneries(diocese_id)

@app.get("/api/deaneries/{deanery_id}")
def get_deanery(deanery_id: int, current_user: dict = Depends(check_permission("Deaneries", "view"))):
    scope = get_user_scope(current_user)
    if not scope["is_all"]:
        if deanery_id != scope.get("deanery_id"):
            raise HTTPException(status_code=403, detail="Access denied. You can only view your assigned deanery.")
    res = db_get_deanery(deanery_id)
    if not res:
        raise HTTPException(status_code=404, detail="Deanery not found")
    return res

@app.post("/api/deaneries")
def create_deanery(deanery: DeaneryModel, current_user: dict = Depends(check_permission("Deaneries", "create"))):
    # Verify diocese exists
    d = db_get_diocese(deanery.diocese_id)
    if not d:
        raise HTTPException(status_code=404, detail="Parent Diocese not found")
    d_id = db_create_deanery(deanery.dict())
    return {"id": d_id, "message": "Deanery created successfully"}

@app.put("/api/deaneries/{deanery_id}")
def update_deanery(deanery_id: int, deanery: DeaneryModel, current_user: dict = Depends(check_permission("Deaneries", "edit"))):
    res = db_get_deanery(deanery_id)
    if not res:
        raise HTTPException(status_code=404, detail="Deanery not found")
    db_update_deanery(deanery_id, deanery.dict())
    return {"message": "Deanery updated successfully"}

@app.delete("/api/deaneries/{deanery_id}")
def delete_deanery(deanery_id: int, current_user: dict = Depends(check_permission("Deaneries", "delete"))):
    res = db_get_deanery(deanery_id)
    if not res:
        raise HTTPException(status_code=404, detail="Deanery not found")
    db_delete_deanery(deanery_id)
    return {"message": "Deanery deleted successfully"}

# Parishes CRUD
@app.get("/api/parishes")
def get_parishes(diocese_id: Optional[int] = None, deanery_id: Optional[int] = None, current_user: dict = Depends(check_permission("Parishes", "view"))):
    scope = get_user_scope(current_user)
    return db_get_parishes(
        diocese_id=diocese_id,
        deanery_id=deanery_id,
        allowed_parish_ids=scope["allowed_parish_ids"] if not scope["is_all"] else None
    )

@app.get("/api/parishes/{parish_id}")
def get_parish(parish_id: int, current_user: dict = Depends(check_permission("Parishes", "view"))):
    scope = get_user_scope(current_user)
    if not scope["is_all"]:
        allowed = scope.get("allowed_parish_ids") or []
        if parish_id not in allowed:
            raise HTTPException(status_code=403, detail="Access denied. You cannot view this parish.")
    res = db_get_parish(parish_id)
    if not res:
        raise HTTPException(status_code=404, detail="Parish not found")
    res["wards"] = db_get_wards_by_parish(parish_id)
    res["groups"] = db_get_groups_by_parish(parish_id)
    return res

@app.post("/api/parishes")
def create_parish(parish: ParishModel, current_user: dict = Depends(check_permission("Parishes", "create"))):
    # Verify deanery and diocese exist
    d = db_get_diocese(parish.diocese_id)
    dn = db_get_deanery(parish.deanery_id)
    if not d or not dn:
        raise HTTPException(status_code=404, detail="Parent Diocese or Deanery not found")
    p_id = db_create_parish(parish.dict())
    return {"id": p_id, "message": "Parish created successfully"}

@app.put("/api/parishes/{parish_id}")
def update_parish(parish_id: int, parish: ParishModel, current_user: dict = Depends(check_permission("Parishes", "edit"))):
    res = db_get_parish(parish_id)
    if not res:
        raise HTTPException(status_code=404, detail="Parish not found")
    db_update_parish(parish_id, parish.dict())
    return {"message": "Parish updated successfully"}

@app.delete("/api/parishes/{parish_id}")
def delete_parish(parish_id: int, current_user: dict = Depends(check_permission("Parishes", "delete"))):
    res = db_get_parish(parish_id)
    if not res:
        raise HTTPException(status_code=404, detail="Parish not found")
    db_delete_parish(parish_id)
    return {"message": "Parish deleted successfully"}

# Wards CRUD
@app.get("/api/wards")
def get_wards(parish_id: int, current_user: dict = Depends(check_permission("Parishes", "view"))):
    return db_get_wards_by_parish(parish_id)

@app.post("/api/wards")
def create_ward(ward: WardModel, current_user: dict = Depends(check_permission("Parishes", "create"))):
    w_id = db_create_ward(ward.dict())
    return {"id": w_id, "message": "Ward created successfully"}

@app.put("/api/wards/{ward_id}")
def update_ward(ward_id: int, ward: WardModel, current_user: dict = Depends(check_permission("Parishes", "edit"))):
    db_update_ward(ward_id, ward.dict())
    return {"message": "Ward updated successfully"}

@app.delete("/api/wards/{ward_id}")
def delete_ward(ward_id: int, current_user: dict = Depends(check_permission("Parishes", "delete"))):
    db_delete_ward(ward_id)
    return {"message": "Ward deleted successfully"}

# Groups CRUD
@app.get("/api/groups")
def get_groups(parish_id: int, current_user: dict = Depends(check_permission("Parishes", "view"))):
    return db_get_groups_by_parish(parish_id)

@app.post("/api/groups")
def create_group(group: GroupModel, current_user: dict = Depends(check_permission("Parishes", "create"))):
    g_id = db_create_group(group.dict())
    return {"id": g_id, "message": "Group created successfully"}

@app.put("/api/groups/{group_id}")
def update_group(group_id: int, group: GroupModel, current_user: dict = Depends(check_permission("Parishes", "edit"))):
    db_update_group(group_id, group.dict())
    return {"message": "Group updated successfully"}

@app.delete("/api/groups/{group_id}")
def delete_group(group_id: int, current_user: dict = Depends(check_permission("Parishes", "delete"))):
    db_delete_group(group_id)
    return {"message": "Group deleted successfully"}

# Families CRUD
@app.get("/api/families")
def get_families(parish_id: Optional[int] = None, current_user: dict = Depends(check_permission("Parishes", "view"))):
    scope = get_user_scope(current_user)
    return db_get_families(
        parish_id=parish_id,
        allowed_parish_ids=scope["allowed_parish_ids"] if not scope["is_all"] else None
    )

@app.get("/api/families/{family_id}")
def get_family(family_id: int, current_user: dict = Depends(check_permission("Parishes", "view"))):
    scope = get_user_scope(current_user)
    res = db_get_family(family_id)
    if not res:
        raise HTTPException(status_code=404, detail="Family not found")
    if not scope["is_all"]:
        allowed = scope.get("allowed_parish_ids") or []
        if res.get("parish_id") not in allowed:
            raise HTTPException(status_code=403, detail="Access denied. You cannot view this family.")
    # Fetch members of this family
    members = db_get_members(family_id=family_id, allowed_parish_ids=scope["allowed_parish_ids"] if not scope["is_all"] else None)
    res["members"] = members
    # Fetch relations of this family
    relations = db_get_family_relations(family_id)
    res["relations"] = relations
    return res

@app.post("/api/families/relations")
def add_family_relation(relation: FamilyRelationModel, current_user: dict = Depends(check_permission("Parishes", "edit"))):
    data = relation.dict()
    transfer = data.pop("transfer_member", False)
    r_id = db_add_family_relation(**data)
    
    # Handle member transfer
    if transfer and relation.member_id:
        member = db_get_member(relation.member_id)
        if member:
            # Move member to the family they are not currently in, typically family2_id
            new_family_id = relation.family2_id if member["family_id"] == relation.family1_id else relation.family1_id
            
            # Make sure we don't overwrite date fields with formatted strings if the db_update expects standard format
            # db_update_member takes dict, but we should reuse the existing logic
            # The safest way is to update the DB directly for just this field to avoid validation issues with full update
            conn = get_db_connection()
            try:
                conn.execute("UPDATE members SET family_id = ? WHERE id = ?", (new_family_id, relation.member_id))
                conn.commit()
            finally:
                conn.close()

    return {"id": r_id, "message": "Family relation added successfully"}

@app.delete("/api/families/relations/{relation_id}")
def delete_family_relation(relation_id: int, current_user: dict = Depends(check_permission("Parishes", "edit"))):
    db_delete_family_relation(relation_id)
    return {"message": "Family relation deleted successfully"}


@app.post("/api/families")
def create_family(family: FamilyModel, current_user: dict = Depends(check_permission("Parishes", "edit"))):
    f_id = db_create_family(family.dict())
    return {"id": f_id, "message": "Family created successfully"}

@app.put("/api/families/{family_id}")
def update_family(family_id: int, family: FamilyModel, current_user: dict = Depends(check_permission("Parishes", "edit"))):
    res = db_get_family(family_id)
    if not res:
        raise HTTPException(status_code=404, detail="Family not found")
    db_update_family(family_id, family.dict())
    return {"message": "Family updated successfully"}

@app.delete("/api/families/{family_id}")
def delete_family(family_id: int, current_user: dict = Depends(check_permission("Parishes", "delete"))):
    res = db_get_family(family_id)
    if not res:
        raise HTTPException(status_code=404, detail="Family not found")
    db_delete_family(family_id)
    return {"message": "Family deleted successfully"}

# Members CRUD
@app.get("/api/members")
def get_members(
    parish_id: Optional[int] = None,
    family_id: Optional[int] = None,
    role: Optional[str] = None,
    search: Optional[str] = None,
    baptism: Optional[bool] = None,
    communion: Optional[bool] = None,
    confirmation: Optional[bool] = None,
    marriage: Optional[bool] = None,
    holy_orders: Optional[bool] = None,
    current_user: dict = Depends(check_permission("Parishioners", "view"))
):
    scope = get_user_scope(current_user)
    return db_get_members(
        parish_id=parish_id,
        family_id=family_id,
        role=role,
        search=search,
        baptism=baptism,
        communion=communion,
        confirmation=confirmation,
        marriage=marriage,
        holy_orders=holy_orders,
        allowed_parish_ids=scope["allowed_parish_ids"] if not scope["is_all"] else None
    )

@app.get("/api/members/{member_id}")
def get_member(member_id: int, current_user: dict = Depends(check_permission("Parishioners", "view"))):
    scope = get_user_scope(current_user)
    res = db_get_member(member_id)
    if not res:
        raise HTTPException(status_code=404, detail="Member not found")
    if not scope["is_all"]:
        allowed = scope.get("allowed_parish_ids") or []
        if res.get("parish_id") not in allowed:
            raise HTTPException(status_code=403, detail="Access denied. You can only view members within your assigned scope.")
    relations = db_get_member_family_relations(member_id)
    res["relations"] = relations
    return res

@app.post("/api/members")
def create_member(member: MemberModel, current_user: dict = Depends(check_permission("Parishioners", "create"))):
    scope = get_user_scope(current_user)
    if not scope["is_all"]:
        allowed = scope.get("allowed_parish_ids") or []
        target_parish = member.parish_id or scope.get("parish_id")
        if not target_parish or target_parish not in allowed:
            raise HTTPException(status_code=403, detail="Access denied. You can only create members within your assigned scope.")
        p = db_get_parish(target_parish)
        if not p:
            raise HTTPException(status_code=404, detail="Parish not found")
        data = member.dict()
        data["parish_id"] = target_parish
    else:
        p = db_get_parish(member.parish_id)
        if not p:
            raise HTTPException(status_code=404, detail="Parish not found")
        data = member.dict()
    m_id = db_create_member(data)
    return {"id": m_id, "message": "Parish member created successfully"}

@app.put("/api/members/{member_id}")
def update_member(member_id: int, member: MemberModel, current_user: dict = Depends(check_permission("Parishioners", "edit"))):
    scope = get_user_scope(current_user)
    res = db_get_member(member_id)
    if not res:
        raise HTTPException(status_code=404, detail="Member not found")
        
    if not scope["is_all"]:
        allowed = scope.get("allowed_parish_ids") or []
        if res.get("parish_id") not in allowed:
            raise HTTPException(status_code=403, detail="Access denied. You can only edit members within your assigned scope.")
            
    target_parish_id = member.parish_id or res.get("parish_id")
    if target_parish_id:
        p = db_get_parish(target_parish_id)
        if not p:
            raise HTTPException(status_code=404, detail="Parish not found")
        if not scope["is_all"] and target_parish_id not in (scope.get("allowed_parish_ids") or []):
            raise HTTPException(status_code=403, detail="Access denied. You cannot assign members outside your assigned scope.")
            
    data = member.dict()
    data["parish_id"] = target_parish_id
    db_update_member(member_id, data)
    return {"message": "Member updated successfully"}

@app.delete("/api/members/{member_id}")
def delete_member(member_id: int, current_user: dict = Depends(check_permission("Parishes", "delete"))):
    scope = get_user_scope(current_user)
    res = db_get_member(member_id)
    if not res:
        raise HTTPException(status_code=404, detail="Member not found")
    if not scope["is_all"]:
        allowed = scope.get("allowed_parish_ids") or []
        if res.get("parish_id") not in allowed:
            raise HTTPException(status_code=403, detail="Access denied. You can only delete members within your assigned scope.")
    db_delete_member(member_id)
    return {"message": "Member deleted successfully"}

# Member Groups Endpoints
@app.post("/api/members/{member_id}/groups")
def add_member_to_group(member_id: int, group: MemberGroupModel, current_user: dict = Depends(check_permission("Parishes", "edit"))):
    mg_id = db_add_member_group(member_id, group.group_id, group.role)
    if not mg_id:
        raise HTTPException(status_code=400, detail="Member is already in this group")
    return {"id": mg_id, "message": "Added to group successfully"}

@app.delete("/api/members/groups/{member_group_id}")
def remove_member_from_group(member_group_id: int, current_user: dict = Depends(check_permission("Parishes", "edit"))):
    db_remove_member_group(member_group_id)
    return {"message": "Removed from group successfully"}

# --- Auth Endpoints ---

@app.post("/api/auth/register")
def register_user(user: UserRegisterModel, current_user: dict = Depends(require_admin)):
    try:
        u_id = db_create_user(user.username, user.password, user.role, user.avatar_url, user.deanery_id, user.parish_id)
        return {"id": u_id, "username": user.username, "role": user.role, "deanery_id": user.deanery_id, "parish_id": user.parish_id, "message": "User created successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/api/auth/users/{user_id}")
def update_user_endpoint(user_id: int, user_data: UserUpdateModel, current_user: dict = Depends(require_admin)):
    try:
        db_update_user(user_id, user_data.dict(exclude_unset=True))
        return {"message": "User updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/auth/login")
def login_user(credentials: UserLoginModel):
    user = db_authenticate_user(credentials.username, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
        
    access_token = create_access_token(data={
        "sub": user["username"],
        "role": user.get("role", "Admin"),
        "uid": user.get("id"),
        "deanery_id": user.get("deanery_id"),
        "parish_id": user.get("parish_id")
    })
    
    return {
        "token": access_token,
        "user": user,
        "message": "Login successful"
    }

@app.get("/api/auth/users")
def get_all_users(current_user: dict = Depends(require_admin)):
    try:
        return db_get_users()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Sacramental Certificates ---
@app.get("/api/members/{member_id}/certificate/{cert_type}")
def get_sacramental_certificate(
    member_id: int,
    cert_type: str,
    current_user: dict = Depends(check_permission("Parishioners", "print"))
):
    scope = get_user_scope(current_user)
    member = db_get_member(member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
        
    if not scope["is_all"]:
        allowed = scope.get("allowed_parish_ids") or []
        if member.get("parish_id") not in allowed:
            raise HTTPException(status_code=403, detail="Access denied. You can only print certificates for your assigned parish.")
            
    valid_types = ("baptism", "communion", "confirmation", "marriage", "holy_orders")
    if cert_type.lower() not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid certificate type. Allowed: {', '.join(valid_types)}")
        
    parish = db_get_parish(member.get("parish_id")) if member.get("parish_id") else None
    diocese = db_get_diocese(parish.get("diocese_id")) if parish and parish.get("diocese_id") else None

    pdf_bytes = generate_sacramental_certificate(cert_type, member, parish, diocese)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename={cert_type}_certificate_{member_id}.pdf"
        }
    )

# --- Events Endpoints ---
@app.get("/api/events")
def get_events(parish_id: Optional[int] = None, current_user: dict = Depends(check_permission("Home", "view"))):
    scope = get_user_scope(current_user)
    return db_get_events(
        parish_id=parish_id,
        allowed_parish_ids=scope["allowed_parish_ids"] if not scope["is_all"] else None
    )

@app.get("/api/events/{event_id}")
def get_event(event_id: int, current_user: dict = Depends(check_permission("Home", "view"))):
    event = db_get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event

@app.post("/api/events")
def create_event(event: EventModel, current_user: dict = Depends(check_permission("Home", "create"))):
    scope = get_user_scope(current_user)
    if not scope["is_all"]:
        allowed = scope.get("allowed_parish_ids") or []
        target_parish = event.parish_id or scope.get("parish_id")
        if not target_parish or target_parish not in allowed:
            raise HTTPException(status_code=403, detail="Access denied. You can only create events for your assigned parish.")
        data = event.dict()
        data["parish_id"] = target_parish
    else:
        data = event.dict()
    e_id = db_create_event(data)
    return {"id": e_id, "message": "Event created successfully"}

@app.put("/api/events/{event_id}")
def update_event(event_id: int, event: EventModel, current_user: dict = Depends(check_permission("Home", "edit"))):
    scope = get_user_scope(current_user)
    existing = db_get_event(event_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Event not found")
    if not scope["is_all"]:
        allowed = scope.get("allowed_parish_ids") or []
        if existing.get("parish_id") not in allowed:
            raise HTTPException(status_code=403, detail="Access denied. You cannot edit this event.")
    db_update_event(event_id, event.dict())
    return {"message": "Event updated successfully"}

@app.delete("/api/events/{event_id}")
def delete_event(event_id: int, current_user: dict = Depends(check_permission("Home", "delete"))):
    scope = get_user_scope(current_user)
    existing = db_get_event(event_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Event not found")
    if not scope["is_all"]:
        allowed = scope.get("allowed_parish_ids") or []
        if existing.get("parish_id") not in allowed:
            raise HTTPException(status_code=403, detail="Access denied. You cannot delete this event.")
    db_delete_event(event_id)
    return {"message": "Event deleted successfully"}

# --- Circulars & Notice Board Endpoints ---
@app.get("/api/circulars")
def get_circulars(
    diocese_id: Optional[int] = None,
    deanery_id: Optional[int] = None,
    parish_id: Optional[int] = None,
    current_user: dict = Depends(check_permission("Home", "view"))
):
    scope = get_user_scope(current_user)
    return db_get_circulars(
        diocese_id=diocese_id,
        deanery_id=deanery_id,
        parish_id=parish_id,
        allowed_parish_ids=scope["allowed_parish_ids"] if not scope["is_all"] else None
    )

@app.get("/api/circulars/{circular_id}")
def get_circular(circular_id: int, current_user: dict = Depends(check_permission("Home", "view"))):
    circ = db_get_circular(circular_id)
    if not circ:
        raise HTTPException(status_code=404, detail="Circular not found")
    return circ

@app.post("/api/circulars")
def create_circular(circular: CircularModel, current_user: dict = Depends(check_permission("Home", "create"))):
    data = circular.dict()
    data["author"] = current_user.get("username", "Chancery Office")
    c_id = db_create_circular(data)
    return {"id": c_id, "message": "Circular published successfully"}

@app.delete("/api/circulars/{circular_id}")
def delete_circular(circular_id: int, current_user: dict = Depends(check_permission("Home", "delete"))):
    circ = db_get_circular(circular_id)
    if not circ:
        raise HTTPException(status_code=404, detail="Circular not found")
    db_delete_circular(circular_id)
    return {"message": "Circular deleted successfully"}

# --- Contributions & Tithes Endpoints ---
@app.get("/api/contributions")
def get_contributions(
    parish_id: Optional[int] = None,
    family_id: Optional[int] = None,
    member_id: Optional[int] = None,
    category: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    current_user: dict = Depends(check_permission("Parishes", "view"))
):
    scope = get_user_scope(current_user)
    return db_get_contributions(
        parish_id=parish_id,
        family_id=family_id,
        member_id=member_id,
        category=category,
        from_date=from_date,
        to_date=to_date,
        allowed_parish_ids=scope["allowed_parish_ids"] if not scope["is_all"] else None
    )

@app.get("/api/contributions/summary")
def get_contributions_summary(parish_id: Optional[int] = None, current_user: dict = Depends(check_permission("Parishes", "view"))):
    scope = get_user_scope(current_user)
    return db_get_contributions_summary(
        parish_id=parish_id,
        allowed_parish_ids=scope["allowed_parish_ids"] if not scope["is_all"] else None
    )

@app.get("/api/contributions/{contribution_id}")
def get_contribution(contribution_id: int, current_user: dict = Depends(check_permission("Parishes", "view"))):
    scope = get_user_scope(current_user)
    c = db_get_contribution(contribution_id)
    if not c:
        raise HTTPException(status_code=404, detail="Contribution not found")
    if not scope["is_all"]:
        allowed = scope.get("allowed_parish_ids") or []
        if c.get("parish_id") not in allowed:
            raise HTTPException(status_code=403, detail="Access denied. You cannot view this contribution.")
    return c

@app.post("/api/contributions")
def create_contribution(contribution: ContributionModel, current_user: dict = Depends(check_permission("Parishes", "create"))):
    scope = get_user_scope(current_user)
    if not scope["is_all"]:
        allowed = scope.get("allowed_parish_ids") or []
        target_parish = contribution.parish_id or scope.get("parish_id")
        if not target_parish or target_parish not in allowed:
            raise HTTPException(status_code=403, detail="Access denied. You can only record contributions for your assigned parish.")
        data = contribution.dict()
        data["parish_id"] = target_parish
    else:
        data = contribution.dict()
    data["recorded_by"] = current_user.get("username", "Office")
    c_id, receipt_no = db_create_contribution(data)
    return {"id": c_id, "receipt_no": receipt_no, "message": "Contribution recorded successfully"}

@app.delete("/api/contributions/{contribution_id}")
def delete_contribution(contribution_id: int, current_user: dict = Depends(check_permission("Parishes", "delete"))):
    scope = get_user_scope(current_user)
    c = db_get_contribution(contribution_id)
    if not c:
        raise HTTPException(status_code=404, detail="Contribution not found")
    if not scope["is_all"]:
        allowed = scope.get("allowed_parish_ids") or []
        if c.get("parish_id") not in allowed:
            raise HTTPException(status_code=403, detail="Access denied. You cannot delete this contribution.")
    db_delete_contribution(contribution_id)
    return {"message": "Contribution deleted successfully"}

@app.get("/api/contributions/{contribution_id}/receipt")
def get_contribution_receipt_pdf(contribution_id: int, current_user: dict = Depends(check_permission("Parishes", "print"))):
    scope = get_user_scope(current_user)
    c = db_get_contribution(contribution_id)
    if not c:
        raise HTTPException(status_code=404, detail="Contribution not found")
    if not scope["is_all"]:
        allowed = scope.get("allowed_parish_ids") or []
        if c.get("parish_id") not in allowed:
            raise HTTPException(status_code=403, detail="Access denied. You cannot view this receipt.")
            
    parish = db_get_parish(c.get("parish_id")) if c.get("parish_id") else None
    member = db_get_member(c.get("member_id")) if c.get("member_id") else None
    family = db_get_family(c.get("family_id")) if c.get("family_id") else None

    pdf_bytes = generate_contribution_receipt(c, parish, member, family)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=receipt_{c.get('receipt_no', contribution_id)}.pdf"}
    )

# --- Export Engine ---
@app.get("/api/export/members")
def export_members(
    format: str = Query("excel", regex="^(excel|csv)$"),
    parish_id: Optional[int] = None,
    current_user: dict = Depends(check_permission("Parishioners", "export"))
):
    scope = get_user_scope(current_user)
    members = db_get_members(
        parish_id=parish_id,
        allowed_parish_ids=scope["allowed_parish_ids"] if not scope["is_all"] else None
    )
    if format == "csv":
        csv_str = export_members_to_csv(members)
        return Response(
            content=csv_str,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=parishioners_directory.csv"}
        )
    else:
        wb_bytes = export_members_to_excel(members)
        return Response(
            content=wb_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=parishioners_directory.xlsx"}
        )

@app.get("/api/export/contributions")
def export_contributions(
    parish_id: Optional[int] = None,
    current_user: dict = Depends(check_permission("Parishes", "export"))
):
    scope = get_user_scope(current_user)
    contributions = db_get_contributions(
        parish_id=parish_id,
        allowed_parish_ids=scope["allowed_parish_ids"] if not scope["is_all"] else None
    )
    wb_bytes = export_contributions_to_excel(contributions)
    return Response(
        content=wb_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=parish_contributions.xlsx"}
    )

# --- Route Aliases for /api/reports/... ---

@app.get("/api/reports/receipt/{contribution_id}")
def get_contribution_receipt_pdf_alias(contribution_id: int, current_user: dict = Depends(check_permission("Parishes", "print"))):
    return get_contribution_receipt_pdf(contribution_id, current_user)

@app.get("/api/reports/certificate/{cert_type}/{member_id}")
def get_sacramental_certificate_alias(cert_type: str, member_id: int, current_user: dict = Depends(check_permission("Parishioners", "print"))):
    return get_sacramental_certificate(member_id=member_id, cert_type=cert_type, current_user=current_user)

@app.get("/api/reports/export/members/excel")
def export_members_excel_alias(parish_id: Optional[int] = None, current_user: dict = Depends(check_permission("Parishioners", "export"))):
    return export_members(format="excel", parish_id=parish_id, current_user=current_user)

@app.get("/api/reports/export/members/csv")
def export_members_csv_alias(parish_id: Optional[int] = None, current_user: dict = Depends(check_permission("Parishioners", "export"))):
    return export_members(format="csv", parish_id=parish_id, current_user=current_user)

@app.get("/api/reports/export/contributions/excel")
def export_contributions_excel_alias(parish_id: Optional[int] = None, current_user: dict = Depends(check_permission("Parishes", "export"))):
    return export_contributions(parish_id=parish_id, current_user=current_user)

# --- Diocesan Commissions, Competitions & Programs Endpoints ---

@app.get("/api/commissions")
def get_commissions(current_user: dict = Depends(get_current_user)):
    return db_get_commissions()

@app.get("/api/commissions/{commission_id}")
def get_commission(commission_id: int, current_user: dict = Depends(get_current_user)):
    res = db_get_commission(commission_id)
    if not res:
        raise HTTPException(status_code=404, detail="Commission not found")
    return res

@app.get("/api/programs")
def get_programs(
    commission_id: Optional[int] = None,
    type: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    scope = get_user_scope(current_user)
    return db_get_programs(
        commission_id=commission_id,
        program_type=type,
        status=status,
        allowed_parish_ids=scope["allowed_parish_ids"] if not scope["is_all"] else None
    )

@app.get("/api/programs/{program_id}")
def get_program(program_id: int, current_user: dict = Depends(get_current_user)):
    res = db_get_program(program_id)
    if not res:
        raise HTTPException(status_code=404, detail="Program not found")
    return res

@app.post("/api/programs")
def create_program(program: ProgramModel, current_user: dict = Depends(check_permission("Home", "create"))):
    scope = get_user_scope(current_user)
    data = program.dict()
    data["created_by"] = current_user.get("username", "Commission Office")
    p_id = db_create_program(data)
    return {"id": p_id, "message": "Program / Competition scheduled successfully"}

@app.put("/api/programs/{program_id}")
def update_program(program_id: int, program: ProgramModel, current_user: dict = Depends(check_permission("Home", "edit"))):
    existing = db_get_program(program_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Program not found")
    db_update_program(program_id, program.dict())
    return {"message": "Program updated successfully"}

@app.delete("/api/programs/{program_id}")
def delete_program(program_id: int, current_user: dict = Depends(check_permission("Home", "delete"))):
    existing = db_get_program(program_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Program not found")
    db_delete_program(program_id)
    return {"message": "Program deleted successfully"}

# --- Participants & Competition Entries ---

@app.get("/api/programs/{program_id}/participants")
def get_program_participants(program_id: int, parish_id: Optional[int] = None, current_user: dict = Depends(get_current_user)):
    return db_get_program_participants(program_id, parish_id=parish_id)

@app.post("/api/programs/{program_id}/participants")
def register_participant(program_id: int, participant: ParticipantRegisterModel, current_user: dict = Depends(check_permission("Parishioners", "create"))):
    scope = get_user_scope(current_user)
    if not scope["is_all"]:
        allowed = scope.get("allowed_parish_ids") or []
        if participant.parish_id not in allowed:
            raise HTTPException(status_code=403, detail="Access denied. You can only register participants from your parish.")
    data = participant.dict()
    data["program_id"] = program_id
    part_id = db_register_participant(data)
    return {"id": part_id, "message": "Participant registered successfully"}

@app.put("/api/programs/participants/{participant_id}")
def update_participant(participant_id: int, payload: ParticipantUpdateModel, current_user: dict = Depends(check_permission("Parishioners", "edit"))):
    existing = db_get_participant(participant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Participant not found")
    update_data = {**existing, **{k: v for k, v in payload.dict().items() if v is not None}}
    db_update_participant(participant_id, update_data)
    return {"message": "Participant details / award updated successfully"}

@app.delete("/api/programs/participants/{participant_id}")
def delete_participant(participant_id: int, current_user: dict = Depends(check_permission("Parishioners", "delete"))):
    existing = db_get_participant(participant_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Participant not found")
    db_delete_participant(participant_id)
    return {"message": "Participant removed successfully"}

# --- Official Program / Competition Certificate (PDF) ---

@app.get("/api/reports/program-certificate/{participant_id}")
def get_program_certificate_pdf(participant_id: int, current_user: dict = Depends(check_permission("Parishioners", "print"))):
    part = db_get_participant(participant_id)
    if not part:
        raise HTTPException(status_code=404, detail="Participant not found")
    prog = db_get_program(part.get("program_id"))
    comm = db_get_commission(prog.get("commission_id")) if prog else None
    parish = db_get_parish(part.get("parish_id")) if part.get("parish_id") else None
    dioceses_list = db_get_dioceses()
    diocese = db_get_diocese(parish.get("diocese_id")) if (parish and parish.get("diocese_id")) else (dioceses_list[0] if dioceses_list else None)

    pdf_bytes = generate_competition_certificate(part, prog, comm, parish, diocese)
    safe_name = part.get("participant_name", "Participant").replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=Certificate_{safe_name}.pdf"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)



