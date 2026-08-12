from fastapi import FastAPI, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional, List
import uuid

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
    db_get_members,
    db_get_member,
    db_create_member,
    db_update_member,
    db_delete_member,
    db_create_user,
    db_authenticate_user,
    db_get_users,
    get_db_connection,
    db_get_permissions,
    db_save_permissions
)

app = FastAPI(title="Diocese ERP API")

# Enable CORS for frontend local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    init_db()

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

class MemberModel(BaseModel):
    parish_id: int
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

class UserRegisterModel(BaseModel):
    username: str
    password: str
    role: Optional[str] = "Admin"
    avatar_url: Optional[str] = None

class UserLoginModel(BaseModel):
    username: str
    password: str

# --- Authentication Helpers ---

def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")
    
    token = authorization.split(" ")[1]
    parts = token.split("-")
    if len(parts) < 4:
        raise HTTPException(status_code=401, detail="Malformed authentication token")
        
    username = parts[3]
    conn = get_db_connection()
    user = conn.execute("SELECT id, username, role FROM users WHERE username = ?", (username,)).fetchone()
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
            
        conn = get_db_connection()
        col = f"can_{action}"
        row = conn.execute(
            f"SELECT {col} FROM role_permissions WHERE LOWER(role) = ? AND LOWER(page) = ?",
            (user_role.lower(), page.lower())
        ).fetchone()
        conn.close()
        
        if not row or row[0] != 1:
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
        return db_get_stats()
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
    return db_get_deaneries(diocese_id)

@app.get("/api/deaneries/{deanery_id}")
def get_deanery(deanery_id: int, current_user: dict = Depends(check_permission("Deaneries", "view"))):
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
    return db_get_parishes(diocese_id, deanery_id)

@app.get("/api/parishes/{parish_id}")
def get_parish(parish_id: int, current_user: dict = Depends(check_permission("Parishes", "view"))):
    res = db_get_parish(parish_id)
    if not res:
        raise HTTPException(status_code=404, detail="Parish not found")
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

# Members CRUD
@app.get("/api/members")
def get_members(
    parish_id: Optional[int] = None,
    role: Optional[str] = None,
    search: Optional[str] = None,
    baptism: Optional[bool] = None,
    communion: Optional[bool] = None,
    confirmation: Optional[bool] = None,
    marriage: Optional[bool] = None,
    holy_orders: Optional[bool] = None,
    current_user: dict = Depends(check_permission("Parishioners", "view"))
):
    return db_get_members(parish_id, role, search, baptism, communion, confirmation, marriage, holy_orders)

@app.get("/api/members/{member_id}")
def get_member(member_id: int, current_user: dict = Depends(check_permission("Parishioners", "view"))):
    res = db_get_member(member_id)
    if not res:
        raise HTTPException(status_code=404, detail="Member not found")
    return res

@app.post("/api/members")
def create_member(member: MemberModel, current_user: dict = Depends(check_permission("Parishioners", "create"))):
    # Verify parish exists
    p = db_get_parish(member.parish_id)
    if not p:
        raise HTTPException(status_code=404, detail="Parish not found")
    m_id = db_create_member(member.dict())
    return {"id": m_id, "message": "Parish member created successfully"}

@app.put("/api/members/{member_id}")
def update_member(member_id: int, member: MemberModel, current_user: dict = Depends(check_permission("Parishioners", "edit"))):
    res = db_get_member(member_id)
    if not res:
        raise HTTPException(status_code=404, detail="Member not found")
    # Verify parish exists
    p = db_get_parish(member.parish_id)
    if not p:
        raise HTTPException(status_code=404, detail="Parish not found")
    db_update_member(member_id, member.dict())
    return {"message": "Member updated successfully"}

@app.delete("/api/members/{member_id}")
def delete_member(member_id: int, current_user: dict = Depends(check_permission("Parishioners", "delete"))):
    res = db_get_member(member_id)
    if not res:
        raise HTTPException(status_code=404, detail="Member not found")
    db_delete_member(member_id)
    return {"message": "Member deleted successfully"}

# --- Auth Endpoints ---

@app.post("/api/auth/register")
def register_user(user: UserRegisterModel, current_user: dict = Depends(require_admin)):
    try:
        u_id = db_create_user(user.username, user.password, user.role, user.avatar_url)
        return {"id": u_id, "username": user.username, "role": user.role, "message": "User created successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/auth/login")
def login_user(credentials: UserLoginModel):
    user = db_authenticate_user(credentials.username, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    # Return user object along with a simple mock token
    return {
        "token": f"session-token-{user['id']}-{user['username']}",
        "user": user,
        "message": "Login successful"
    }

@app.get("/api/auth/users")
def get_all_users(current_user: dict = Depends(require_admin)):
    try:
        return db_get_users()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
