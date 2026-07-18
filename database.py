import pymysql
import pymysql.cursors
import os
import hashlib

MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "shine30")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "scd")

def hash_password(password: str) -> str:
    salt = "diocese_secret_salt"
    return hashlib.sha256((password + salt).encode('utf-8')).hexdigest()

class RowWrapper(dict):
    def __init__(self, d):
        super().__init__(d)
        self._list_values = list(d.values())
        
    def __getitem__(self, key):
        if isinstance(key, int):
            try:
                return self._list_values[key]
            except IndexError:
                raise KeyError(key)
        return super().__getitem__(key)

class CursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor
        
    @property
    def lastrowid(self):
        return self.cursor.lastrowid
        
    def execute(self, sql, params=None):
        sql_converted = sql.replace("?", "%s")
        self.cursor.execute(sql_converted, params or ())
        return self
        
    def fetchone(self):
        row = self.cursor.fetchone()
        return RowWrapper(row) if row else None
        
    def fetchall(self):
        rows = self.cursor.fetchall()
        return [RowWrapper(r) for r in rows] if rows else []

class MySQLConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn
        
    def execute(self, sql, params=None):
        sql_converted = sql.replace("?", "%s")
        cursor = self.conn.cursor()
        cursor.execute(sql_converted, params or ())
        return CursorWrapper(cursor)
        
    def cursor(self):
        return CursorWrapper(self.conn.cursor())
        
    def commit(self):
        self.conn.commit()
        
    def close(self):
        self.conn.close()

def get_db():
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()

def get_db_connection():
    conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        cursorclass=pymysql.cursors.DictCursor
    )
    return MySQLConnectionWrapper(conn)

def init_db():
    # Connect without specifying database to create it if it doesn't exist
    conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD
    )
    cursor = conn.cursor()
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_DATABASE}")
    conn.commit()
    conn.close()

    # Connect to the specified database to create tables
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Dioceses Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dioceses (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        bishop VARCHAR(255),
        founded VARCHAR(255),
        email VARCHAR(255),
        phone VARCHAR(255),
        address VARCHAR(255)
    );
    """)

    # 2. Deaneries Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS deaneries (
        id INT AUTO_INCREMENT PRIMARY KEY,
        diocese_id INT NOT NULL,
        name VARCHAR(255) NOT NULL,
        dean VARCHAR(255),
        description TEXT,
        FOREIGN KEY (diocese_id) REFERENCES dioceses(id) ON DELETE CASCADE
    );
    """)

    # 3. Parishes Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS parishes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        deanery_id INT NOT NULL,
        diocese_id INT NOT NULL,
        name VARCHAR(255) NOT NULL,
        pastor VARCHAR(255),
        assistant_pastor VARCHAR(255),
        address VARCHAR(255),
        phone VARCHAR(255),
        email VARCHAR(255),
        FOREIGN KEY (deanery_id) REFERENCES deaneries(id) ON DELETE CASCADE,
        FOREIGN KEY (diocese_id) REFERENCES dioceses(id) ON DELETE CASCADE
    );
    """)

    # 4. Members Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS members (
        id INT AUTO_INCREMENT PRIMARY KEY,
        parish_id INT NOT NULL,
        first_name VARCHAR(255) NOT NULL,
        last_name VARCHAR(255) NOT NULL,
        gender VARCHAR(50),
        dob VARCHAR(50),
        email VARCHAR(255),
        phone VARCHAR(255),
        address VARCHAR(255),
        role VARCHAR(255),
        
        baptism_received INTEGER DEFAULT 0,
        baptism_date VARCHAR(50),
        baptism_parish VARCHAR(255),
        
        communion_received INTEGER DEFAULT 0,
        communion_date VARCHAR(50),
        communion_parish VARCHAR(255),
        
        confirmation_received INTEGER DEFAULT 0,
        confirmation_date VARCHAR(50),
        confirmation_parish VARCHAR(255),
        
        marriage_received INTEGER DEFAULT 0,
        marriage_date VARCHAR(50),
        marriage_parish VARCHAR(255),
        
        holy_orders_received INTEGER DEFAULT 0,
        holy_orders_date VARCHAR(50),
        holy_orders_parish VARCHAR(255),
        
        FOREIGN KEY (parish_id) REFERENCES parishes(id) ON DELETE CASCADE
    );
    """)

    # 5. Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(255) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role VARCHAR(255) DEFAULT 'Admin'
    );
    """)

    # 6. Role Permissions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS role_permissions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        role VARCHAR(255) NOT NULL,
        page VARCHAR(255) NOT NULL,
        can_create TINYINT DEFAULT 0,
        can_view TINYINT DEFAULT 0,
        can_edit TINYINT DEFAULT 0,
        can_delete TINYINT DEFAULT 0,
        can_export TINYINT DEFAULT 0,
        can_print TINYINT DEFAULT 0,
        can_send TINYINT DEFAULT 0,
        UNIQUE KEY unique_role_page (role, page)
    );
    """)
    conn.commit()

    # Seed data if empty
    cursor.execute("SELECT COUNT(*) FROM dioceses")
    if cursor.fetchone()[0] == 0:
        diocese_id = 1
        deanery_id_1 = 1
        deanery_id_2 = 2
        parish_id_1 = 1
        parish_id_2 = 2
        parish_id_3 = 3

        # Seed Diocese
        cursor.execute("""
        INSERT INTO dioceses (id, name, bishop, founded, email, phone, address)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            diocese_id,
            "Archdiocese of Seattle",
            "Most Rev. Paul D. Etienne",
            "1850",
            "chancery@seattlearch.org",
            "+1 (206) 382-4560",
            "910 Marion St, Seattle, WA 98104"
        ))

        # Seed Deaneries
        cursor.execute("""
        INSERT INTO deaneries (id, diocese_id, name, dean, description)
        VALUES (?, ?, ?, ?, ?)
        """, (
            deanery_id_1,
            diocese_id,
            "Seattle Deanery",
            "Very Rev. Michael G. Ryan",
            "Deanery covering core Seattle parishes"
        ))
        cursor.execute("""
        INSERT INTO deaneries (id, diocese_id, name, dean, description)
        VALUES (?, ?, ?, ?, ?)
        """, (
            deanery_id_2,
            diocese_id,
            "South King Deanery",
            "Very Rev. John Vance",
            "Deanery covering cities south of Seattle"
        ))

        # Seed Parishes
        cursor.execute("""
        INSERT INTO parishes (id, deanery_id, diocese_id, name, pastor, assistant_pastor, address, phone, email)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            parish_id_1,
            deanery_id_1,
            diocese_id,
            "St. James Cathedral",
            "Rev. Michael G. Ryan",
            "Rev. Kyle R. DeVore",
            "804 9th Ave, Seattle, WA 98104",
            "+1 (206) 622-3559",
            "info@stjames-cathedral.org"
        ))
        cursor.execute("""
        INSERT INTO parishes (id, deanery_id, diocese_id, name, pastor, assistant_pastor, address, phone, email)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            parish_id_2,
            deanery_id_1,
            diocese_id,
            "St. Joseph Parish",
            "Rev. Chris F. Del Real",
            "Rev. Laura M. Martinez",
            "732 18th Ave E, Seattle, WA 98112",
            "+1 (206) 324-2522",
            "info@stjosephparish.org"
        ))
        cursor.execute("""
        INSERT INTO parishes (id, deanery_id, diocese_id, name, pastor, assistant_pastor, address, phone, email)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            parish_id_3,
            deanery_id_2,
            diocese_id,
            "St. Stephen the Martyr",
            "Rev. Edward J. White",
            "Rev. Michael S. Patrick",
            "13055 SE 192nd St, Renton, WA 98058",
            "+1 (425) 255-3132",
            "office@ststephensl.org"
        ))

        # Seed Members
        members_data = [
            (
                1, parish_id_1, "John", "Doe", "Male", "1985-06-15",
                "john.doe@gmail.com", "+1 (206) 555-0101", "101 Pike St, Seattle, WA", "Laity",
                1, "1985-08-20", "St. James Cathedral",
                1, "1993-05-12", "St. James Cathedral",
                1, "2001-04-18", "St. James Cathedral",
                1, "2010-09-04", "St. James Cathedral",
                0, None, None
            ),
            (
                2, parish_id_1, "Mary", "Jane", "Female", "1990-09-22",
                "mary.jane@gmail.com", "+1 (206) 555-0102", "204 Pine St, Seattle, WA", "Laity",
                1, "1990-11-15", "St. Joseph Parish",
                1, "1998-05-20", "St. Joseph Parish",
                1, "2006-05-18", "St. Joseph Parish",
                0, None, None,
                0, None, None
            ),
            (
                3, parish_id_2, "Rev. Chris", "Del Real", "Male", "1975-03-10",
                "pastor@stjosephparish.org", "+1 (206) 324-2522", "732 18th Ave E, Seattle, WA", "Priest",
                1, "1975-04-12", "St. Mary Church",
                1, "1983-05-15", "St. Mary Church",
                1, "1991-04-20", "St. Mary Church",
                0, None, None,
                1, "2003-06-08", "St. James Cathedral"
            ),
            (
                4, parish_id_3, "Robert", "Johnson", "Male", "2008-11-05",
                "robert.j@outlook.com", "+1 (425) 555-0133", "202 Sunset Blvd, Renton, WA", "Laity",
                1, "2009-01-10", "St. Stephen the Martyr",
                1, "2016-05-15", "St. Stephen the Martyr",
                0, None, None,
                0, None, None,
                0, None, None
            )
        ]

        for m in members_data:
            cursor.execute("""
            INSERT INTO members (
                id, parish_id, first_name, last_name, gender, dob, email, phone, address, role,
                baptism_received, baptism_date, baptism_parish,
                communion_received, communion_date, communion_parish,
                confirmation_received, confirmation_date, confirmation_parish,
                marriage_received, marriage_date, marriage_parish,
                holy_orders_received, holy_orders_date, holy_orders_parish
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, m)
            
        conn.commit()

    # Seed Admin User if empty
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO users (username, password_hash, role)
        VALUES (?, ?, ?)
        """, ("admin", hash_password("admin123"), "Admin"))
        conn.commit()

    # Seed Default Permissions if empty
    cursor.execute("SELECT COUNT(*) FROM role_permissions")
    if cursor.fetchone()[0] == 0:
        default_perms = [
            # Administrator
            ("Administrator", "Home", 1, 1, 1, 1, 1, 1, 1),
            ("Administrator", "Diocese", 1, 1, 1, 1, 1, 1, 1),
            ("Administrator", "Deaneries", 1, 1, 1, 1, 1, 1, 1),
            ("Administrator", "Parishes", 1, 1, 1, 1, 1, 1, 1),
            ("Administrator", "Parishioners", 1, 1, 1, 1, 1, 1, 1),
            ("Administrator", "Users", 1, 1, 1, 1, 1, 1, 1),
            ("Administrator", "Permissions", 1, 1, 1, 1, 1, 1, 1),
            
            # Admin (compatibility/fallback)
            ("Admin", "Home", 1, 1, 1, 1, 1, 1, 1),
            ("Admin", "Diocese", 1, 1, 1, 1, 1, 1, 1),
            ("Admin", "Deaneries", 1, 1, 1, 1, 1, 1, 1),
            ("Admin", "Parishes", 1, 1, 1, 1, 1, 1, 1),
            ("Admin", "Parishioners", 1, 1, 1, 1, 1, 1, 1),
            ("Admin", "Users", 1, 1, 1, 1, 1, 1, 1),
            ("Admin", "Permissions", 1, 1, 1, 1, 1, 1, 1),

            # Bishop
            ("Bishop", "Home", 0, 1, 0, 0, 0, 1, 0),
            ("Bishop", "Diocese", 1, 1, 1, 1, 1, 1, 0),
            ("Bishop", "Deaneries", 1, 1, 1, 1, 1, 1, 0),
            ("Bishop", "Parishes", 0, 1, 0, 0, 1, 1, 0),
            ("Bishop", "Parishioners", 0, 1, 0, 0, 1, 1, 0),
            ("Bishop", "Users", 0, 0, 0, 0, 0, 0, 0),
            ("Bishop", "Permissions", 0, 0, 0, 0, 0, 0, 0),

            # Dean
            ("Dean", "Home", 0, 1, 0, 0, 0, 1, 0),
            ("Dean", "Diocese", 0, 0, 0, 0, 0, 0, 0),
            ("Dean", "Deaneries", 0, 1, 0, 0, 1, 1, 0),
            ("Dean", "Parishes", 1, 1, 1, 1, 1, 1, 1),
            ("Dean", "Parishioners", 0, 1, 0, 0, 1, 1, 0),
            ("Dean", "Users", 0, 0, 0, 0, 0, 0, 0),
            ("Dean", "Permissions", 0, 0, 0, 0, 0, 0, 0),

            # Parish Priest
            ("Parish Priest", "Home", 0, 1, 0, 0, 0, 1, 0),
            ("Parish Priest", "Diocese", 0, 0, 0, 0, 0, 0, 0),
            ("Parish Priest", "Deaneries", 0, 1, 0, 0, 0, 0, 0),
            ("Parish Priest", "Parishes", 0, 1, 0, 0, 1, 1, 0),
            ("Parish Priest", "Parishioners", 1, 1, 1, 1, 1, 1, 1),
            ("Parish Priest", "Users", 0, 0, 0, 0, 0, 0, 0),
            ("Parish Priest", "Permissions", 0, 0, 0, 0, 0, 0, 0),

            # Sisters
            ("Sisters", "Home", 0, 1, 0, 0, 0, 0, 0),
            ("Sisters", "Diocese", 0, 0, 0, 0, 0, 0, 0),
            ("Sisters", "Deaneries", 0, 0, 0, 0, 0, 0, 0),
            ("Sisters", "Parishes", 0, 1, 0, 0, 0, 1, 0),
            ("Sisters", "Parishioners", 0, 1, 0, 0, 0, 1, 0),
            ("Sisters", "Users", 0, 0, 0, 0, 0, 0, 0),
            ("Sisters", "Permissions", 0, 0, 0, 0, 0, 0, 0),

            # Lay people
            ("Lay people", "Home", 0, 1, 0, 0, 0, 0, 0),
            ("Lay people", "Diocese", 0, 0, 0, 0, 0, 0, 0),
            ("Lay people", "Deaneries", 0, 0, 0, 0, 0, 0, 0),
            ("Lay people", "Parishes", 0, 1, 0, 0, 0, 0, 0),
            ("Lay people", "Parishioners", 0, 1, 0, 0, 0, 0, 0),
            ("Lay people", "Users", 0, 0, 0, 0, 0, 0, 0),
            ("Lay people", "Permissions", 0, 0, 0, 0, 0, 0, 0),

            # Youth
            ("Youth", "Home", 0, 1, 0, 0, 0, 0, 0),
            ("Youth", "Diocese", 0, 0, 0, 0, 0, 0, 0),
            ("Youth", "Deaneries", 0, 0, 0, 0, 0, 0, 0),
            ("Youth", "Parishes", 0, 1, 0, 0, 0, 0, 0),
            ("Youth", "Parishioners", 0, 1, 0, 0, 0, 0, 0),
            ("Youth", "Users", 0, 0, 0, 0, 0, 0, 0),
            ("Youth", "Permissions", 0, 0, 0, 0, 0, 0, 0),
        ]
        for role, page, c, v, e, d, ex, pr, sd in default_perms:
            cursor.execute("""
            INSERT INTO role_permissions (role, page, can_create, can_view, can_edit, can_delete, can_export, can_print, can_send)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (role, page, c, v, e, d, ex, pr, sd))
        conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")

# --- CRUD helper functions ---

# Users / Authentication
def db_create_user(username, password, role="Admin"):
    conn = get_db_connection()
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if row:
        conn.close()
        raise Exception("Username already exists")
    
    cursor = conn.execute("""
    INSERT INTO users (username, password_hash, role)
    VALUES (?, ?, ?)
    """, (username, hash_password(password), role))
    conn.commit()
    u_id = cursor.lastrowid
    conn.close()
    return u_id

def db_authenticate_user(username, password):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if row and row["password_hash"] == hash_password(password):
        user_dict = dict(row)
        user_dict.pop("password_hash")
        return user_dict
    return None

def db_get_users():
    conn = get_db_connection()
    rows = conn.execute("SELECT id, username, role FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# Dioceses
def db_get_dioceses():
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM dioceses").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_get_diocese(diocese_id):
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM dioceses WHERE id = ?", (diocese_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def db_create_diocese(data):
    conn = get_db_connection()
    cursor = conn.execute("""
    INSERT INTO dioceses (name, bishop, founded, email, phone, address)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (data["name"], data.get("bishop"), data.get("founded"), data.get("email"), data.get("phone"), data.get("address")))
    conn.commit()
    d_id = cursor.lastrowid
    conn.close()
    return d_id

def db_update_diocese(diocese_id, data):
    conn = get_db_connection()
    conn.execute("""
    UPDATE dioceses SET name = ?, bishop = ?, founded = ?, email = ?, phone = ?, address = ? WHERE id = ?
    """, (data["name"], data.get("bishop"), data.get("founded"), data.get("email"), data.get("phone"), data.get("address"), diocese_id))
    conn.commit()
    conn.close()
    return True

def db_delete_diocese(diocese_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM dioceses WHERE id = ?", (diocese_id,))
    conn.commit()
    conn.close()
    return True

# Deaneries
def db_get_deaneries(diocese_id=None):
    conn = get_db_connection()
    if diocese_id:
        rows = conn.execute("SELECT d.*, o.name as diocese_name FROM deaneries d JOIN dioceses o ON d.diocese_id = o.id WHERE d.diocese_id = ?", (diocese_id,)).fetchall()
    else:
        rows = conn.execute("SELECT d.*, o.name as diocese_name FROM deaneries d JOIN dioceses o ON d.diocese_id = o.id").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_get_deanery(deanery_id):
    conn = get_db_connection()
    row = conn.execute("SELECT d.*, o.name as diocese_name FROM deaneries d JOIN dioceses o ON d.diocese_id = o.id WHERE d.id = ?", (deanery_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def db_create_deanery(data):
    conn = get_db_connection()
    cursor = conn.execute("""
    INSERT INTO deaneries (diocese_id, name, dean, description)
    VALUES (?, ?, ?, ?)
    """, (data["diocese_id"], data["name"], data.get("dean"), data.get("description")))
    conn.commit()
    d_id = cursor.lastrowid
    conn.close()
    return d_id

def db_update_deanery(deanery_id, data):
    conn = get_db_connection()
    conn.execute("""
    UPDATE deaneries SET name = ?, dean = ?, description = ? WHERE id = ?
    """, (data["name"], data.get("dean"), data.get("description"), deanery_id))
    conn.commit()
    conn.close()
    return True

def db_delete_deanery(deanery_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM deaneries WHERE id = ?", (deanery_id,))
    conn.commit()
    conn.close()
    return True

# Parishes
def db_get_parishes(diocese_id=None, deanery_id=None):
    conn = get_db_connection()
    query = """
        SELECT p.*, o.name as diocese_name, d.name as deanery_name 
        FROM parishes p 
        JOIN dioceses o ON p.diocese_id = o.id 
        JOIN deaneries d ON p.deanery_id = d.id
    """
    params = []
    conditions = []
    if diocese_id:
        conditions.append("p.diocese_id = ?")
        params.append(diocese_id)
    if deanery_id:
        conditions.append("p.deanery_id = ?")
        params.append(deanery_id)
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_get_parish(parish_id):
    conn = get_db_connection()
    row = conn.execute("""
        SELECT p.*, o.name as diocese_name, d.name as deanery_name 
        FROM parishes p 
        JOIN dioceses o ON p.diocese_id = o.id 
        JOIN deaneries d ON p.deanery_id = d.id
        WHERE p.id = ?
    """, (parish_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def db_create_parish(data):
    conn = get_db_connection()
    cursor = conn.execute("""
    INSERT INTO parishes (deanery_id, diocese_id, name, pastor, assistant_pastor, address, phone, email)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (data["deanery_id"], data["diocese_id"], data["name"], data.get("pastor"), data.get("assistant_pastor"), data.get("address"), data.get("phone"), data.get("email")))
    conn.commit()
    p_id = cursor.lastrowid
    conn.close()
    return p_id

def db_update_parish(parish_id, data):
    conn = get_db_connection()
    conn.execute("""
    UPDATE parishes SET name = ?, pastor = ?, assistant_pastor = ?, address = ?, phone = ?, email = ? WHERE id = ?
    """, (data["name"], data.get("pastor"), data.get("assistant_pastor"), data.get("address"), data.get("phone"), data.get("email"), parish_id))
    conn.commit()
    conn.close()
    return True

def db_delete_parish(parish_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM parishes WHERE id = ?", (parish_id,))
    conn.commit()
    conn.close()
    return True

# Members
def db_get_members(parish_id=None, role=None, search=None, baptism=None, communion=None, confirmation=None, marriage=None, holy_orders=None):
    conn = get_db_connection()
    query = """
        SELECT m.*, p.name as parish_name, d.name as deanery_name, o.name as diocese_name
        FROM members m
        JOIN parishes p ON m.parish_id = p.id
        JOIN deaneries d ON p.deanery_id = d.id
        JOIN dioceses o ON p.diocese_id = o.id
    """
    params = []
    conditions = []
    
    if parish_id:
        conditions.append("m.parish_id = ?")
        params.append(parish_id)
    if role:
        conditions.append("m.role = ?")
        params.append(role)
    if search:
        conditions.append("(m.first_name LIKE ? OR m.last_name LIKE ? OR m.email LIKE ? OR m.phone LIKE ?)")
        search_param = f"%{search}%"
        params.extend([search_param, search_param, search_param, search_param])
    if baptism is not None:
        conditions.append("m.baptism_received = ?")
        params.append(1 if baptism else 0)
    if communion is not None:
        conditions.append("m.communion_received = ?")
        params.append(1 if communion else 0)
    if confirmation is not None:
        conditions.append("m.confirmation_received = ?")
        params.append(1 if confirmation else 0)
    if marriage is not None:
        conditions.append("m.marriage_received = ?")
        params.append(1 if marriage else 0)
    if holy_orders is not None:
        conditions.append("m.holy_orders_received = ?")
        params.append(1 if holy_orders else 0)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_get_member(member_id):
    conn = get_db_connection()
    row = conn.execute("""
        SELECT m.*, p.name as parish_name, d.name as deanery_name, o.name as diocese_name
        FROM members m
        JOIN parishes p ON m.parish_id = p.id
        JOIN deaneries d ON p.deanery_id = d.id
        JOIN dioceses o ON p.diocese_id = o.id
        WHERE m.id = ?
    """, (member_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def db_create_member(data):
    conn = get_db_connection()
    cursor = conn.execute("""
    INSERT INTO members (
        parish_id, first_name, last_name, gender, dob, email, phone, address, role,
        baptism_received, baptism_date, baptism_parish,
        communion_received, communion_date, communion_parish,
        confirmation_received, confirmation_date, confirmation_parish,
        marriage_received, marriage_date, marriage_parish,
        holy_orders_received, holy_orders_date, holy_orders_parish
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["parish_id"], data["first_name"], data["last_name"], data.get("gender"), data.get("dob"),
        data.get("email"), data.get("phone"), data.get("address"), data.get("role", "Laity"),
        1 if data.get("baptism_received") else 0, data.get("baptism_date"), data.get("baptism_parish"),
        1 if data.get("communion_received") else 0, data.get("communion_date"), data.get("communion_parish"),
        1 if data.get("confirmation_received") else 0, data.get("confirmation_date"), data.get("confirmation_parish"),
        1 if data.get("marriage_received") else 0, data.get("marriage_date"), data.get("marriage_parish"),
        1 if data.get("holy_orders_received") else 0, data.get("holy_orders_date"), data.get("holy_orders_parish")
    ))
    conn.commit()
    m_id = cursor.lastrowid
    conn.close()
    return m_id

def db_update_member(member_id, data):
    conn = get_db_connection()
    conn.execute("""
    UPDATE members SET 
        first_name = ?, last_name = ?, gender = ?, dob = ?, email = ?, phone = ?, address = ?, role = ?,
        baptism_received = ?, baptism_date = ?, baptism_parish = ?,
        communion_received = ?, communion_date = ?, communion_parish = ?,
        confirmation_received = ?, confirmation_date = ?, confirmation_parish = ?,
        marriage_received = ?, marriage_date = ?, marriage_parish = ?,
        holy_orders_received = ?, holy_orders_date = ?, holy_orders_parish = ?
    WHERE id = ?
    """, (
        data["first_name"], data["last_name"], data.get("gender"), data.get("dob"),
        data.get("email"), data.get("phone"), data.get("address"), data.get("role", "Laity"),
        1 if data.get("baptism_received") else 0, data.get("baptism_date"), data.get("baptism_parish"),
        1 if data.get("communion_received") else 0, data.get("communion_date"), data.get("communion_parish"),
        1 if data.get("confirmation_received") else 0, data.get("confirmation_date"), data.get("confirmation_parish"),
        1 if data.get("marriage_received") else 0, data.get("marriage_date"), data.get("marriage_parish"),
        1 if data.get("holy_orders_received") else 0, data.get("holy_orders_date"), data.get("holy_orders_parish"),
        member_id
    ))
    conn.commit()
    conn.close()
    return True

def db_delete_member(member_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM members WHERE id = ?", (member_id,))
    conn.commit()
    conn.close()
    return True

# Stats & Overview
def db_get_stats():
    conn = get_db_connection()
    
    # Counts
    dioceses_count = conn.execute("SELECT COUNT(*) FROM dioceses").fetchone()[0]
    deaneries_count = conn.execute("SELECT COUNT(*) FROM deaneries").fetchone()[0]
    parishes_count = conn.execute("SELECT COUNT(*) FROM parishes").fetchone()[0]
    members_count = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    
    # Role distribution
    role_rows = conn.execute("SELECT role, COUNT(*) as count FROM members GROUP BY role").fetchall()
    role_dist = {r["role"]: r["count"] for r in role_rows}
    
    # Sacrament rates
    sacraments = {
        "baptism": conn.execute("SELECT COUNT(*) FROM members WHERE baptism_received = 1").fetchone()[0],
        "communion": conn.execute("SELECT COUNT(*) FROM members WHERE communion_received = 1").fetchone()[0],
        "confirmation": conn.execute("SELECT COUNT(*) FROM members WHERE confirmation_received = 1").fetchone()[0],
        "marriage": conn.execute("SELECT COUNT(*) FROM members WHERE marriage_received = 1").fetchone()[0],
        "holy_orders": conn.execute("SELECT COUNT(*) FROM members WHERE holy_orders_received = 1").fetchone()[0],
    }
    
    # Recent members
    recent_rows = conn.execute("""
        SELECT m.id, m.first_name, m.last_name, m.role, p.name as parish_name 
        FROM members m 
        JOIN parishes p ON m.parish_id = p.id 
        ORDER BY m.id DESC LIMIT 5
    """).fetchall()
    recent_members = [dict(r) for r in recent_rows]
    
    conn.close()
    
    return {
        "counts": {
            "dioceses": dioceses_count,
            "deaneries": deaneries_count,
            "parishes": parishes_count,
            "members": members_count
        },
        "role_distribution": role_dist,
        "sacrament_counts": sacraments,
        "recent_members": recent_members
    }

def db_get_permissions(role: str = None):
    conn = get_db_connection()
    if role:
        rows = conn.execute("SELECT * FROM role_permissions WHERE role = ?", (role,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM role_permissions").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_save_permissions(role: str, perms: list):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        for p in perms:
            cursor.execute("""
            INSERT INTO role_permissions (role, page, can_create, can_view, can_edit, can_delete, can_export, can_print, can_send)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
                can_create = VALUES(can_create),
                can_view = VALUES(can_view),
                can_edit = VALUES(can_edit),
                can_delete = VALUES(can_delete),
                can_export = VALUES(can_export),
                can_print = VALUES(can_print),
                can_send = VALUES(can_send)
            """, (
                role,
                p["page"],
                int(p.get("can_create", 0)),
                int(p.get("can_view", 0)),
                int(p.get("can_edit", 0)),
                int(p.get("can_delete", 0)),
                int(p.get("can_export", 0)),
                int(p.get("can_print", 0)),
                int(p.get("can_send", 0))
            ))
        conn.commit()
    finally:
        conn.close()
