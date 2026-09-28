import pymysql
import pymysql.cursors
import os
import hashlib
from queue import Queue, Empty
import threading
import time
from datetime import datetime

MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "shine30")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "scd")

def hash_password(password: str) -> str:
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    except Exception:
        salt = "diocese_secret_salt"
        return hashlib.sha256((password + salt).encode('utf-8')).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password or not plain_password:
        return False
    # Bcrypt hash support ($2a$, $2b$, $2y$)
    if hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            import bcrypt
            return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception:
            pass
    # SHA-256 with salt support
    salt = "diocese_secret_salt"
    if hashlib.sha256((plain_password + salt).encode('utf-8')).hexdigest() == hashed_password:
        return True
    # Plain SHA-256 support
    if hashlib.sha256(plain_password.encode('utf-8')).hexdigest() == hashed_password:
        return True
    # Direct equality fallback
    if plain_password == hashed_password:
        return True
    return False

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

class MySQLConnectionPool:
    def __init__(self, size=15):
        self.size = size
        self.pool = Queue(maxsize=size)
        
    def _create_connection(self):
        ssl_config = None
        if "aivencloud.com" in MYSQL_HOST:
            ssl_config = {"ssl": {}}
        return pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            cursorclass=pymysql.cursors.DictCursor,
            ssl=ssl_config,
            connect_timeout=10,
            autocommit=True
        )
        
    def get_connection(self):
        # Queue.get_nowait() is atomic and thread-safe without an external lock
        try:
            conn = self.pool.get_nowait()
        except Empty:
            return self._create_connection()

        # Ping remote DB without holding a global lock so other requests proceed in parallel
        try:
            conn.ping(reconnect=True)
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            return self._create_connection()
                
    def release_connection(self, conn):
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            self.pool.put_nowait(conn)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

# Global pool instance
_global_db_pool = None
_pool_lock = threading.Lock()

def get_db_pool():
    global _global_db_pool
    with _pool_lock:
        if _global_db_pool is None:
            _global_db_pool = MySQLConnectionPool(size=15)
        return _global_db_pool

class MySQLConnectionWrapper:
    def __init__(self, conn, pool):
        self.conn = conn
        self.pool = pool
        
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
        self.pool.release_connection(self.conn)

def get_db():
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()

def get_db_connection():
    pool = get_db_pool()
    conn = pool.get_connection()
    return MySQLConnectionWrapper(conn, pool)

def init_db():
    ssl_config = None
    if "aivencloud.com" in MYSQL_HOST:
        ssl_config = {"ssl": {}}
    # Connect without specifying database to create it if it doesn't exist
    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            ssl=ssl_config,
            connect_timeout=10
        )
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_DATABASE}")
        conn.commit()
        conn.close()
    except Exception:
        pass

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
        avatar_url VARCHAR(500) NULL,
        
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
        role VARCHAR(255) DEFAULT 'Admin',
        avatar_url VARCHAR(500) NULL,
        deanery_id INT NULL,
        parish_id INT NULL,
        FOREIGN KEY (deanery_id) REFERENCES deaneries(id) ON DELETE SET NULL,
        FOREIGN KEY (parish_id) REFERENCES parishes(id) ON DELETE SET NULL
    );
    """)
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN deanery_id INT NULL")
        cursor.execute("ALTER TABLE users ADD CONSTRAINT fk_user_deanery FOREIGN KEY (deanery_id) REFERENCES deaneries(id) ON DELETE SET NULL")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN parish_id INT NULL")
        cursor.execute("ALTER TABLE users ADD CONSTRAINT fk_user_parish FOREIGN KEY (parish_id) REFERENCES parishes(id) ON DELETE SET NULL")
    except Exception:
        pass

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

    # 7. Wards Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS wards (
        id INT AUTO_INCREMENT PRIMARY KEY,
        parish_id INT NOT NULL,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (parish_id) REFERENCES parishes(id) ON DELETE CASCADE
    );
    """)

    # 8. Groups Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS `groups` (
        id INT AUTO_INCREMENT PRIMARY KEY,
        parish_id INT NOT NULL,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (parish_id) REFERENCES parishes(id) ON DELETE CASCADE
    );
    """)

    # 9. Member Groups Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS member_groups (
        id INT AUTO_INCREMENT PRIMARY KEY,
        member_id INT NOT NULL,
        group_id INT NOT NULL,
        role VARCHAR(255) NOT NULL DEFAULT 'Member',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
        FOREIGN KEY (group_id) REFERENCES `groups`(id) ON DELETE CASCADE
    );
    """)

    # 10. Families Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS families (
        id INT AUTO_INCREMENT PRIMARY KEY,
        parish_id INT NOT NULL,
        ward_id INT,
        name VARCHAR(255) NOT NULL,
        address TEXT,
        phone VARCHAR(255),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (parish_id) REFERENCES parishes(id) ON DELETE CASCADE,
        FOREIGN KEY (ward_id) REFERENCES wards(id) ON DELETE SET NULL
    );
    """)

    # 11. Family Relations Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS family_relations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        family1_id INT NOT NULL,
        family2_id INT NOT NULL,
        member_id INT,
        relationship_type VARCHAR(255) NOT NULL,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (family1_id) REFERENCES families(id) ON DELETE CASCADE,
        FOREIGN KEY (family2_id) REFERENCES families(id) ON DELETE CASCADE,
        FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE SET NULL
    );
    """)

    # 12. Events & Mass Timings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INT AUTO_INCREMENT PRIMARY KEY,
        parish_id INT NULL,
        diocese_id INT NULL,
        title VARCHAR(255) NOT NULL,
        description TEXT,
        event_type VARCHAR(100) DEFAULT 'Mass',
        start_time VARCHAR(50) NOT NULL,
        end_time VARCHAR(50) NULL,
        location VARCHAR(255) NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (parish_id) REFERENCES parishes(id) ON DELETE CASCADE,
        FOREIGN KEY (diocese_id) REFERENCES dioceses(id) ON DELETE CASCADE
    );
    """)

    # 13. Circulars & Announcements Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS circulars (
        id INT AUTO_INCREMENT PRIMARY KEY,
        diocese_id INT NULL,
        deanery_id INT NULL,
        parish_id INT NULL,
        title VARCHAR(255) NOT NULL,
        content TEXT NOT NULL,
        priority VARCHAR(50) DEFAULT 'Normal',
        author VARCHAR(255) NULL,
        publish_date VARCHAR(50) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (diocese_id) REFERENCES dioceses(id) ON DELETE CASCADE,
        FOREIGN KEY (deanery_id) REFERENCES deaneries(id) ON DELETE CASCADE,
        FOREIGN KEY (parish_id) REFERENCES parishes(id) ON DELETE CASCADE
    );
    """)

    # 14. Contributions & Tithes Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS contributions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        parish_id INT NOT NULL,
        family_id INT NULL,
        member_id INT NULL,
        category VARCHAR(100) NOT NULL,
        amount DECIMAL(10, 2) NOT NULL,
        payment_method VARCHAR(50) DEFAULT 'Cash',
        reference_no VARCHAR(100) NULL,
        receipt_no VARCHAR(100) UNIQUE NOT NULL,
        payment_date VARCHAR(50) NOT NULL,
        notes TEXT NULL,
        recorded_by VARCHAR(255) NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (parish_id) REFERENCES parishes(id) ON DELETE CASCADE,
        FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE SET NULL,
        FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE SET NULL
    );
    """)
    conn.commit()

    # Alter tables safe check to add columns if they do not exist
    try:
        cursor.execute("ALTER TABLE members ADD COLUMN avatar_url VARCHAR(500) NULL")
        conn.commit()
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE members ADD COLUMN family_id INT NULL")
        conn.commit()
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN avatar_url VARCHAR(500) NULL")
        conn.commit()
    except Exception:
        pass

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
def get_user_scope(user: dict) -> dict:
    """
    Determines data visibility scope based on role:
    - Administrator / Admin: Diocese/Global wide (all parishes and members)
    - Bishop: Diocese/Global wide (all parishes and members)
    - Dean: Particular deanery parishes and their members
    - Other roles (Parish Priest, Sisters, Lay people, Youth, etc.): Only their own parish members
    """
    role = (user.get("role") or "").strip().lower()
    
    if role in ("admin", "administrator", "bishop"):
        return {
            "is_all": True,
            "role": user.get("role"),
            "deanery_id": None,
            "parish_id": None,
            "allowed_parish_ids": None
        }
        
    user_id = user.get("id")
    deanery_id = user.get("deanery_id")
    parish_id = user.get("parish_id")
    username = (user.get("username") or "").strip()
    
    conn = get_db_connection()
    try:
        # 1. Fetch user record if deanery_id or parish_id are missing
        if user_id and (deanery_id is None or parish_id is None):
            u_row = conn.execute("SELECT deanery_id, parish_id FROM users WHERE id = ?", (user_id,)).fetchone()
            if u_row:
                if deanery_id is None:
                    deanery_id = u_row.get("deanery_id")
                if parish_id is None:
                    parish_id = u_row.get("parish_id")
                    
        # 2. Fallback resolution for parish_id if not explicitly set
        if parish_id is None and username:
            m_row = conn.execute(
                "SELECT parish_id FROM members WHERE LOWER(first_name) = LOWER(?) OR LOWER(email) = LOWER(?) LIMIT 1",
                (username, username)
            ).fetchone()
            if m_row and m_row.get("parish_id"):
                parish_id = m_row.get("parish_id")
                
        # 3. If role is Dean:
        if role == "dean":
            if deanery_id is None and parish_id is not None:
                p_row = conn.execute("SELECT deanery_id FROM parishes WHERE id = ?", (parish_id,)).fetchone()
                if p_row and p_row.get("deanery_id"):
                    deanery_id = p_row.get("deanery_id")
                    
            if deanery_id is None and username:
                d_row = conn.execute("SELECT id FROM deaneries WHERE LOWER(dean) LIKE LOWER(?) LIMIT 1", (f"%{username}%",)).fetchone()
                if d_row:
                    deanery_id = d_row.get("id")
                    
            allowed_parish_ids = []
            if deanery_id is not None:
                rows = conn.execute("SELECT id FROM parishes WHERE deanery_id = ?", (deanery_id,)).fetchall()
                allowed_parish_ids = [r["id"] for r in rows]
                
            return {
                "is_all": False,
                "role": "Dean",
                "deanery_id": deanery_id,
                "parish_id": parish_id,
                "allowed_parish_ids": allowed_parish_ids
            }
            
        # 4. Other roles (Parish Priest, Sisters, Lay people, Youth, etc.)
        allowed_parish_ids = [parish_id] if parish_id is not None else []
        return {
            "is_all": False,
            "role": user.get("role"),
            "deanery_id": deanery_id,
            "parish_id": parish_id,
            "allowed_parish_ids": allowed_parish_ids
        }
    finally:
        conn.close()

def db_create_user(username, password, role="Admin", avatar_url=None, deanery_id=None, parish_id=None):
    conn = get_db_connection()
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if row:
        conn.close()
        raise Exception("Username already exists")
    
    cursor = conn.execute("""
    INSERT INTO users (username, password_hash, role, avatar_url, deanery_id, parish_id)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (username, hash_password(password), role, avatar_url, deanery_id, parish_id))
    conn.commit()
    u_id = cursor.lastrowid
    conn.close()
    return u_id

def db_update_user(user_id, data):
    conn = get_db_connection()
    updates = []
    params = []
    if "role" in data and data["role"] is not None:
        updates.append("role = ?")
        params.append(data["role"])
    if "avatar_url" in data and data["avatar_url"] is not None:
        updates.append("avatar_url = ?")
        params.append(data["avatar_url"])
    if "deanery_id" in data:
        updates.append("deanery_id = ?")
        params.append(data["deanery_id"])
    if "parish_id" in data:
        updates.append("parish_id = ?")
        params.append(data["parish_id"])
    if "password" in data and data["password"]:
        updates.append("password_hash = ?")
        params.append(hash_password(data["password"]))
    if updates:
        params.append(user_id)
        conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
    conn.close()
    return True

def db_authenticate_user(username, password):
    if not username or not password:
        return None
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM users WHERE LOWER(TRIM(username)) = LOWER(?)", (username.strip(),)).fetchone()
    conn.close()
    if row and verify_password(password, row["password_hash"]):
        user_dict = dict(row)
        user_dict.pop("password_hash", None)
        return user_dict
    return None

def db_get_users():
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT u.id, u.username, u.role, u.avatar_url, u.deanery_id, u.parish_id,
               d.name as deanery_name, p.name as parish_name
        FROM users u
        LEFT JOIN deaneries d ON u.deanery_id = d.id
        LEFT JOIN parishes p ON u.parish_id = p.id
    """).fetchall()
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
def db_get_parishes(diocese_id=None, deanery_id=None, allowed_parish_ids=None):
    conn = get_db_connection()
    query = """
        SELECT p.*, o.name as diocese_name, d.name as deanery_name 
        FROM parishes p 
        LEFT JOIN dioceses o ON p.diocese_id = o.id 
        LEFT JOIN deaneries d ON p.deanery_id = d.id
    """
    params = []
    conditions = []
    if allowed_parish_ids is not None:
        if not allowed_parish_ids:
            conn.close()
            return []
        placeholders = ",".join(["?"] * len(allowed_parish_ids))
        conditions.append(f"p.id IN ({placeholders})")
        params.extend(allowed_parish_ids)
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
def db_get_members(parish_id=None, family_id=None, role=None, search=None, baptism=None, communion=None, confirmation=None, marriage=None, holy_orders=None, allowed_parish_ids=None):
    conn = get_db_connection()
    query = """
        SELECT m.*, p.name as parish_name, d.name as deanery_name, o.name as diocese_name
        FROM members m
        LEFT JOIN parishes p ON m.parish_id = p.id
        LEFT JOIN deaneries d ON p.deanery_id = d.id
        LEFT JOIN dioceses o ON p.diocese_id = o.id
    """
    params = []
    conditions = []
    
    if allowed_parish_ids is not None:
        if not allowed_parish_ids:
            conn.close()
            return []
        if parish_id:
            if parish_id in allowed_parish_ids:
                conditions.append("m.parish_id = ?")
                params.append(parish_id)
            else:
                conn.close()
                return []
        else:
            placeholders = ",".join(["?"] * len(allowed_parish_ids))
            conditions.append(f"m.parish_id IN ({placeholders})")
            params.extend(allowed_parish_ids)
    elif parish_id:
        conditions.append("m.parish_id = ?")
        params.append(parish_id)
        
    if family_id:
        conditions.append("m.family_id = ?")
        params.append(family_id)
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
        LEFT JOIN parishes p ON m.parish_id = p.id
        LEFT JOIN deaneries d ON p.deanery_id = d.id
        LEFT JOIN dioceses o ON p.diocese_id = o.id
        WHERE m.id = ?
    """, (member_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def db_create_member(data):
    conn = get_db_connection()
    cursor = conn.execute("""
    INSERT INTO members (
        parish_id, family_id, first_name, last_name, gender, dob, email, phone, address, role, avatar_url,
        baptism_received, baptism_date, baptism_parish,
        communion_received, communion_date, communion_parish,
        confirmation_received, confirmation_date, confirmation_parish,
        marriage_received, marriage_date, marriage_parish,
        holy_orders_received, holy_orders_date, holy_orders_parish
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["parish_id"], data.get("family_id"), data["first_name"], data["last_name"], data.get("gender"), data.get("dob"),
        data.get("email"), data.get("phone"), data.get("address"), data.get("role", "Laity"), data.get("avatar_url"),
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
        parish_id = COALESCE(?, parish_id),
        family_id = ?, first_name = ?, last_name = ?, gender = ?, dob = ?, email = ?, phone = ?, address = ?, role = ?, avatar_url = ?,
        baptism_received = ?, baptism_date = ?, baptism_parish = ?,
        communion_received = ?, communion_date = ?, communion_parish = ?,
        confirmation_received = ?, confirmation_date = ?, confirmation_parish = ?,
        marriage_received = ?, marriage_date = ?, marriage_parish = ?,
        holy_orders_received = ?, holy_orders_date = ?, holy_orders_parish = ?
    WHERE id = ?
    """, (
        data.get("parish_id"),
        data.get("family_id"), data["first_name"], data["last_name"], data.get("gender"), data.get("dob"),
        data.get("email"), data.get("phone"), data.get("address"), data.get("role", "Laity"), data.get("avatar_url"),
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
def db_get_stats(allowed_parish_ids=None):
    conn = get_db_connection()
    try:
        if allowed_parish_ids is not None:
            if not allowed_parish_ids:
                return {
                    "counts": {"dioceses": 0, "deaneries": 0, "parishes": 0, "members": 0},
                    "role_distribution": {},
                    "sacrament_counts": {"baptism": 0, "communion": 0, "confirmation": 0, "marriage": 0, "holy_orders": 0},
                    "recent_members": []
                }
            placeholders = ",".join(["?"] * len(allowed_parish_ids))
            parishes_count = len(allowed_parish_ids)
            deaneries_count = conn.execute(
                f"SELECT COUNT(DISTINCT deanery_id) FROM parishes WHERE id IN ({placeholders}) AND deanery_id IS NOT NULL",
                allowed_parish_ids
            ).fetchone()[0]
            dioceses_count = 1
            members_count = conn.execute(
                f"SELECT COUNT(*) FROM members WHERE parish_id IN ({placeholders})",
                allowed_parish_ids
            ).fetchone()[0]
            
            role_rows = conn.execute(
                f"SELECT role, COUNT(*) as count FROM members WHERE parish_id IN ({placeholders}) GROUP BY role",
                allowed_parish_ids
            ).fetchall()
            role_dist = {r["role"]: r["count"] for r in role_rows}
            
            sacraments = {
                "baptism": conn.execute(f"SELECT COUNT(*) FROM members WHERE baptism_received = 1 AND parish_id IN ({placeholders})", allowed_parish_ids).fetchone()[0],
                "communion": conn.execute(f"SELECT COUNT(*) FROM members WHERE communion_received = 1 AND parish_id IN ({placeholders})", allowed_parish_ids).fetchone()[0],
                "confirmation": conn.execute(f"SELECT COUNT(*) FROM members WHERE confirmation_received = 1 AND parish_id IN ({placeholders})", allowed_parish_ids).fetchone()[0],
                "marriage": conn.execute(f"SELECT COUNT(*) FROM members WHERE marriage_received = 1 AND parish_id IN ({placeholders})", allowed_parish_ids).fetchone()[0],
                "holy_orders": conn.execute(f"SELECT COUNT(*) FROM members WHERE holy_orders_received = 1 AND parish_id IN ({placeholders})", allowed_parish_ids).fetchone()[0],
            }
            
            recent_rows = conn.execute(f"""
                SELECT m.id, m.first_name, m.last_name, m.role, p.name as parish_name 
                FROM members m 
                LEFT JOIN parishes p ON m.parish_id = p.id 
                WHERE m.parish_id IN ({placeholders})
                ORDER BY m.id DESC LIMIT 5
            """, allowed_parish_ids).fetchall()
            recent_members = [dict(r) for r in recent_rows]
            
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
        else:
            dioceses_count = conn.execute("SELECT COUNT(*) FROM dioceses").fetchone()[0]
            deaneries_count = conn.execute("SELECT COUNT(*) FROM deaneries").fetchone()[0]
            parishes_count = conn.execute("SELECT COUNT(*) FROM parishes").fetchone()[0]
            members_count = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
            
            role_rows = conn.execute("SELECT role, COUNT(*) as count FROM members GROUP BY role").fetchall()
            role_dist = {r["role"]: r["count"] for r in role_rows}
            
            sacraments = {
                "baptism": conn.execute("SELECT COUNT(*) FROM members WHERE baptism_received = 1").fetchone()[0],
                "communion": conn.execute("SELECT COUNT(*) FROM members WHERE communion_received = 1").fetchone()[0],
                "confirmation": conn.execute("SELECT COUNT(*) FROM members WHERE confirmation_received = 1").fetchone()[0],
                "marriage": conn.execute("SELECT COUNT(*) FROM members WHERE marriage_received = 1").fetchone()[0],
                "holy_orders": conn.execute("SELECT COUNT(*) FROM members WHERE holy_orders_received = 1").fetchone()[0],
            }
            
            recent_rows = conn.execute("""
                SELECT m.id, m.first_name, m.last_name, m.role, p.name as parish_name 
                FROM members m 
                LEFT JOIN parishes p ON m.parish_id = p.id 
                ORDER BY m.id DESC LIMIT 5
            """).fetchall()
            recent_members = [dict(r) for r in recent_rows]
            
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
    finally:
        conn.close()

_permissions_cache = {}
_permissions_cache_ttl = 300  # 5 minutes

def db_get_permissions(role: str = None):
    cache_key = role.lower() if role else "__all__"
    now = time.time()
    if cache_key in _permissions_cache:
        cached_time, cached_data = _permissions_cache[cache_key]
        if now - cached_time < _permissions_cache_ttl:
            return cached_data

    conn = get_db_connection()
    try:
        if role:
            rows = conn.execute("SELECT * FROM role_permissions WHERE role = ?", (role,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM role_permissions").fetchall()
        result = [dict(r) for r in rows]
        _permissions_cache[cache_key] = (now, result)
        return result
    finally:
        conn.close()

def db_save_permissions(role: str, perms: list):
    _permissions_cache.clear()
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

def db_get_bootstrap_data(allowed_parish_ids=None, deanery_id=None):
    conn = get_db_connection()
    try:
        dioceses = [dict(r) for r in conn.execute("SELECT * FROM dioceses").fetchall()]
        
        # Deaneries
        if deanery_id:
            deaneries = [dict(r) for r in conn.execute(
                "SELECT d.*, o.name as diocese_name FROM deaneries d LEFT JOIN dioceses o ON d.diocese_id = o.id WHERE d.id = ?",
                (deanery_id,)
            ).fetchall()]
        elif allowed_parish_ids is not None:
            if not allowed_parish_ids:
                deaneries = []
            else:
                placeholders = ",".join(["?"] * len(allowed_parish_ids))
                deaneries = [dict(r) for r in conn.execute(
                    f"SELECT DISTINCT d.*, o.name as diocese_name FROM deaneries d LEFT JOIN dioceses o ON d.diocese_id = o.id JOIN parishes p ON p.deanery_id = d.id WHERE p.id IN ({placeholders})",
                    allowed_parish_ids
                ).fetchall()]
        else:
            deaneries = [dict(r) for r in conn.execute(
                "SELECT d.*, o.name as diocese_name FROM deaneries d LEFT JOIN dioceses o ON d.diocese_id = o.id"
            ).fetchall()]
            
        # Parishes
        if allowed_parish_ids is not None:
            if not allowed_parish_ids:
                parishes = []
            else:
                placeholders = ",".join(["?"] * len(allowed_parish_ids))
                parishes = [dict(r) for r in conn.execute(
                    f"SELECT p.*, o.name as diocese_name, d.name as deanery_name FROM parishes p LEFT JOIN dioceses o ON p.diocese_id = o.id LEFT JOIN deaneries d ON p.deanery_id = d.id WHERE p.id IN ({placeholders})",
                    allowed_parish_ids
                ).fetchall()]
        else:
            parishes = [dict(r) for r in conn.execute(
                "SELECT p.*, o.name as diocese_name, d.name as deanery_name FROM parishes p LEFT JOIN dioceses o ON p.diocese_id = o.id LEFT JOIN deaneries d ON p.deanery_id = d.id"
            ).fetchall()]
            
        # Members
        if allowed_parish_ids is not None:
            if not allowed_parish_ids:
                members = []
            else:
                placeholders = ",".join(["?"] * len(allowed_parish_ids))
                members = [dict(r) for r in conn.execute(
                    f"SELECT m.*, p.name as parish_name, d.name as deanery_name, o.name as diocese_name FROM members m LEFT JOIN parishes p ON m.parish_id = p.id LEFT JOIN deaneries d ON p.deanery_id = d.id LEFT JOIN dioceses o ON p.diocese_id = o.id WHERE m.parish_id IN ({placeholders})",
                    allowed_parish_ids
                ).fetchall()]
        else:
            members = [dict(r) for r in conn.execute(
                "SELECT m.*, p.name as parish_name, d.name as deanery_name, o.name as diocese_name FROM members m LEFT JOIN parishes p ON m.parish_id = p.id LEFT JOIN deaneries d ON p.deanery_id = d.id LEFT JOIN dioceses o ON p.diocese_id = o.id"
            ).fetchall()]
            
        return {
            "dioceses": dioceses,
            "deaneries": deaneries,
            "parishes": parishes,
            "members": members
        }
    finally:
        conn.close()

# --- Wards CRUD ---
def db_create_ward(ward_data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO wards (parish_id, name, description)
    VALUES (?, ?, ?)
    """, (ward_data["parish_id"], ward_data["name"], ward_data.get("description", "")))
    conn.commit()
    w_id = cursor.lastrowid
    conn.close()
    return w_id

def db_get_wards_by_parish(parish_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM wards WHERE parish_id = ?", (parish_id,))
    res = cursor.fetchall()
    conn.close()
    return res

def db_update_ward(ward_id, ward_data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE wards SET parish_id = ?, name = ?, description = ? WHERE id = ?
    """, (ward_data["parish_id"], ward_data["name"], ward_data.get("description", ""), ward_id))
    conn.commit()
    conn.close()
    return True

def db_delete_ward(ward_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM wards WHERE id = ?", (ward_id,))
    cursor.execute("UPDATE families SET ward_id = NULL WHERE ward_id = ?", (ward_id,))
    conn.commit()
    conn.close()
    return True

# --- Groups CRUD ---
def db_create_group(group_data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO `groups` (parish_id, name, description)
    VALUES (?, ?, ?)
    """, (group_data["parish_id"], group_data["name"], group_data.get("description", "")))
    conn.commit()
    g_id = cursor.lastrowid
    conn.close()
    return g_id

def db_get_groups_by_parish(parish_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM `groups` WHERE parish_id = ?", (parish_id,))
    res = cursor.fetchall()
    conn.close()
    return res

def db_update_group(group_id, group_data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE `groups` SET parish_id = ?, name = ?, description = ? WHERE id = ?
    """, (group_data["parish_id"], group_data["name"], group_data.get("description", ""), group_id))
    conn.commit()
    conn.close()
    return True

def db_delete_group(group_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM `groups` WHERE id = ?", (group_id,))
    cursor.execute("DELETE FROM member_groups WHERE group_id = ?", (group_id,))
    conn.commit()
    conn.close()
    return True

# --- Member Groups ---
def db_add_member_group(member_id, group_id, role="Member"):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM member_groups WHERE member_id = ? AND group_id = ?", (member_id, group_id))
    if cursor.fetchone():
        conn.close()
        return None
    cursor.execute("""
    INSERT INTO member_groups (member_id, group_id, role)
    VALUES (?, ?, ?)
    """, (member_id, group_id, role))
    conn.commit()
    mg_id = cursor.lastrowid
    conn.close()
    return mg_id

def db_remove_member_group(member_group_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM member_groups WHERE id = ?", (member_group_id,))
    conn.commit()
    conn.close()
    return True

# --- Families CRUD ---
def db_get_families(parish_id=None, allowed_parish_ids=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if allowed_parish_ids is not None:
        if not allowed_parish_ids:
            conn.close()
            return []
        if parish_id:
            if parish_id in allowed_parish_ids:
                cursor.execute("SELECT f.*, w.name as ward_name FROM families f LEFT JOIN wards w ON f.ward_id = w.id WHERE f.parish_id = ?", (parish_id,))
            else:
                conn.close()
                return []
        else:
            placeholders = ",".join(["?"] * len(allowed_parish_ids))
            cursor.execute(f"SELECT f.*, w.name as ward_name FROM families f LEFT JOIN wards w ON f.ward_id = w.id WHERE f.parish_id IN ({placeholders})", allowed_parish_ids)
    elif parish_id:
        cursor.execute("SELECT f.*, w.name as ward_name FROM families f LEFT JOIN wards w ON f.ward_id = w.id WHERE f.parish_id = ?", (parish_id,))
    else:
        cursor.execute("SELECT f.*, w.name as ward_name FROM families f LEFT JOIN wards w ON f.ward_id = w.id")
    res = cursor.fetchall()
    conn.close()
    return res

def db_get_family(family_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT f.*, w.name as ward_name FROM families f LEFT JOIN wards w ON f.ward_id = w.id WHERE f.id = ?", (family_id,))
    res = cursor.fetchone()
    conn.close()
    return res

def db_create_family(family_data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO families (parish_id, ward_id, name, address, phone)
    VALUES (?, ?, ?, ?, ?)
    """, (family_data["parish_id"], family_data.get("ward_id"), family_data["name"], family_data.get("address", ""), family_data.get("phone", "")))
    conn.commit()
    f_id = cursor.lastrowid
    conn.close()
    return f_id

def db_update_family(family_id, family_data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE families 
    SET parish_id = ?, ward_id = ?, name = ?, address = ?, phone = ?
    WHERE id = ?
    """, (family_data["parish_id"], family_data.get("ward_id"), family_data["name"], family_data.get("address", ""), family_data.get("phone", ""), family_id))
    conn.commit()
    conn.close()
    return True

def db_delete_family(family_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM families WHERE id = ?", (family_id,))
    cursor.execute("UPDATE members SET family_id = NULL WHERE family_id = ?", (family_id,))
    conn.commit()
    conn.close()
    return True

# --- Family Relations ---
def db_get_family_relations(family_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT r.*, f1.name as family1_name, f2.name as family2_name, m.first_name, m.last_name 
    FROM family_relations r
    JOIN families f1 ON r.family1_id = f1.id
    JOIN families f2 ON r.family2_id = f2.id
    LEFT JOIN members m ON r.member_id = m.id
    WHERE r.family1_id = ? OR r.family2_id = ?
    """, (family_id, family_id))
    res = cursor.fetchall()
    conn.close()
    return res

def db_get_member_family_relations(member_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT r.*, f1.name as family1_name, f2.name as family2_name
    FROM family_relations r
    JOIN families f1 ON r.family1_id = f1.id
    JOIN families f2 ON r.family2_id = f2.id
    WHERE r.member_id = ?
    """, (member_id,))
    res = cursor.fetchall()
    conn.close()
    return res

def db_add_family_relation(family1_id, family2_id, relationship_type, member_id=None, notes=""):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO family_relations (family1_id, family2_id, member_id, relationship_type, notes)
    VALUES (?, ?, ?, ?, ?)
    """, (family1_id, family2_id, member_id, relationship_type, notes))
    conn.commit()
    r_id = cursor.lastrowid
    conn.close()
    return r_id

def db_delete_family_relation(relation_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM family_relations WHERE id = ?", (relation_id,))
    conn.commit()
    conn.close()
    return True

# --- Events CRUD ---
def db_get_events(parish_id=None, allowed_parish_ids=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    conditions = []
    params = []
    
    if allowed_parish_ids is not None:
        if not allowed_parish_ids:
            # Can still view diocese-wide events (parish_id is NULL)
            conditions.append("e.parish_id IS NULL")
        else:
            placeholders = ",".join(["?"] * len(allowed_parish_ids))
            conditions.append(f"(e.parish_id IN ({placeholders}) OR e.parish_id IS NULL)")
            params.extend(allowed_parish_ids)
    elif parish_id:
        conditions.append("(e.parish_id = ? OR e.parish_id IS NULL)")
        params.append(parish_id)

    sql = """
        SELECT e.*, p.name as parish_name 
        FROM events e 
        LEFT JOIN parishes p ON e.parish_id = p.id
    """
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY e.start_time ASC"

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return rows

def db_get_event(event_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.*, p.name as parish_name 
        FROM events e 
        LEFT JOIN parishes p ON e.parish_id = p.id
        WHERE e.id = ?
    """, (event_id,))
    res = cursor.fetchone()
    conn.close()
    return res

def db_create_event(data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO events (parish_id, diocese_id, title, description, event_type, start_time, end_time, location)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("parish_id"), data.get("diocese_id"), data["title"], data.get("description", ""),
        data.get("event_type", "Mass"), data["start_time"], data.get("end_time"), data.get("location")
    ))
    conn.commit()
    e_id = cursor.lastrowid
    conn.close()
    return e_id

def db_update_event(event_id, data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE events 
        SET parish_id = ?, diocese_id = ?, title = ?, description = ?, event_type = ?, start_time = ?, end_time = ?, location = ?
        WHERE id = ?
    """, (
        data.get("parish_id"), data.get("diocese_id"), data["title"], data.get("description", ""),
        data.get("event_type", "Mass"), data["start_time"], data.get("end_time"), data.get("location"),
        event_id
    ))
    conn.commit()
    conn.close()
    return True

def db_delete_event(event_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
    return True

# --- Circulars & Announcements CRUD ---
def db_get_circulars(diocese_id=None, deanery_id=None, parish_id=None, allowed_parish_ids=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    conditions = []
    params = []

    if allowed_parish_ids is not None:
        if not allowed_parish_ids:
            conditions.append("(c.parish_id IS NULL AND c.deanery_id IS NULL)")
        else:
            placeholders = ",".join(["?"] * len(allowed_parish_ids))
            conditions.append(f"(c.parish_id IN ({placeholders}) OR (c.parish_id IS NULL AND (c.deanery_id IS NULL OR c.deanery_id IN (SELECT deanery_id FROM parishes WHERE id IN ({placeholders})))))")
            params.extend(allowed_parish_ids)
            params.extend(allowed_parish_ids)
    elif parish_id:
        conditions.append("(c.parish_id = ? OR c.parish_id IS NULL)")
        params.append(parish_id)

    sql = """
        SELECT c.*, p.name as parish_name, d.name as deanery_name, o.name as diocese_name
        FROM circulars c
        LEFT JOIN parishes p ON c.parish_id = p.id
        LEFT JOIN deaneries d ON c.deanery_id = d.id
        LEFT JOIN dioceses o ON c.diocese_id = o.id
    """
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY c.publish_date DESC, c.id DESC"

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return rows

def db_get_circular(circular_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, p.name as parish_name, d.name as deanery_name, o.name as diocese_name
        FROM circulars c
        LEFT JOIN parishes p ON c.parish_id = p.id
        LEFT JOIN deaneries d ON c.deanery_id = d.id
        LEFT JOIN dioceses o ON c.diocese_id = o.id
        WHERE c.id = ?
    """, (circular_id,))
    res = cursor.fetchone()
    conn.close()
    return res

def db_create_circular(data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO circulars (diocese_id, deanery_id, parish_id, title, content, priority, author, publish_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("diocese_id"), data.get("deanery_id"), data.get("parish_id"),
        data["title"], data["content"], data.get("priority", "Normal"),
        data.get("author", "Chancery Office"), data.get("publish_date", datetime.now().strftime("%Y-%m-%d"))
    ))
    conn.commit()
    c_id = cursor.lastrowid
    conn.close()
    return c_id

def db_delete_circular(circular_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM circulars WHERE id = ?", (circular_id,))
    conn.commit()
    conn.close()
    return True

# --- Contributions & Tithes CRUD ---
def db_get_contributions(parish_id=None, family_id=None, member_id=None, category=None, from_date=None, to_date=None, allowed_parish_ids=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    conditions = []
    params = []

    if allowed_parish_ids is not None:
        if not allowed_parish_ids:
            conn.close()
            return []
        if parish_id:
            if parish_id in allowed_parish_ids:
                conditions.append("c.parish_id = ?")
                params.append(parish_id)
            else:
                conn.close()
                return []
        else:
            placeholders = ",".join(["?"] * len(allowed_parish_ids))
            conditions.append(f"c.parish_id IN ({placeholders})")
            params.extend(allowed_parish_ids)
    elif parish_id:
        conditions.append("c.parish_id = ?")
        params.append(parish_id)

    if family_id:
        conditions.append("c.family_id = ?")
        params.append(family_id)
    if member_id:
        conditions.append("c.member_id = ?")
        params.append(member_id)
    if category:
        conditions.append("c.category = ?")
        params.append(category)
    if from_date:
        conditions.append("c.payment_date >= ?")
        params.append(from_date)
    if to_date:
        conditions.append("c.payment_date <= ?")
        params.append(to_date)

    sql = """
        SELECT c.*, p.name as parish_name,
               CONCAT(m.first_name, ' ', m.last_name) as member_name,
               f.name as family_name
        FROM contributions c
        LEFT JOIN parishes p ON c.parish_id = p.id
        LEFT JOIN members m ON c.member_id = m.id
        LEFT JOIN families f ON c.family_id = f.id
    """
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY c.payment_date DESC, c.id DESC"

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return rows

def db_get_contribution(contribution_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, p.name as parish_name,
               CONCAT(m.first_name, ' ', m.last_name) as member_name,
               f.name as family_name
        FROM contributions c
        LEFT JOIN parishes p ON c.parish_id = p.id
        LEFT JOIN members m ON c.member_id = m.id
        LEFT JOIN families f ON c.family_id = f.id
        WHERE c.id = ?
    """, (contribution_id,))
    res = cursor.fetchone()
    conn.close()
    return res

def db_create_contribution(data):
    conn = get_db_connection()
    cursor = conn.cursor()

    receipt_no = data.get("receipt_no")
    if not receipt_no:
        year = datetime.now().year
        cursor.execute("SELECT COUNT(*) FROM contributions WHERE receipt_no LIKE ?", (f"REC-{year}-%",))
        count = cursor.fetchone()[0] + 1
        receipt_no = f"REC-{year}-{count:05d}"

    cursor.execute("""
        INSERT INTO contributions (
            parish_id, family_id, member_id, category, amount, payment_method, reference_no, receipt_no, payment_date, notes, recorded_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["parish_id"], data.get("family_id"), data.get("member_id"),
        data["category"], float(data["amount"]), data.get("payment_method", "Cash"),
        data.get("reference_no"), receipt_no, data.get("payment_date", datetime.now().strftime("%Y-%m-%d")),
        data.get("notes"), data.get("recorded_by")
    ))
    conn.commit()
    c_id = cursor.lastrowid
    conn.close()
    return c_id, receipt_no

def db_delete_contribution(contribution_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM contributions WHERE id = ?", (contribution_id,))
    conn.commit()
    conn.close()
    return True

def db_get_contributions_summary(parish_id=None, allowed_parish_ids=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    conditions = []
    params = []

    if allowed_parish_ids is not None:
        if not allowed_parish_ids:
            conn.close()
            return {"total_amount": 0.0, "by_category": {}, "count": 0}
        placeholders = ",".join(["?"] * len(allowed_parish_ids))
        conditions.append(f"parish_id IN ({placeholders})")
        params.extend(allowed_parish_ids)
    elif parish_id:
        conditions.append("parish_id = ?")
        params.append(parish_id)

    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    cursor.execute(f"SELECT COALESCE(SUM(amount), 0) as total, COUNT(*) as cnt FROM contributions{where_clause}", params)
    row = cursor.fetchone()
    total = float(row["total"])
    count = int(row["cnt"])

    cursor.execute(f"SELECT category, COALESCE(SUM(amount), 0) as subtotal, COUNT(*) as cnt FROM contributions{where_clause} GROUP BY category", params)
    cat_rows = cursor.fetchall()
    by_category = {r["category"]: {"total": float(r["subtotal"]), "count": int(r["cnt"])} for r in cat_rows}

    conn.close()
    return {
        "total_amount": total,
        "total_transactions": count,
        "by_category": by_category
    }

# ==============================================================================
# Commissions, Competitions & Programs
# ==============================================================================

def db_get_commissions():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, 
               (SELECT COUNT(*) FROM commission_programs cp WHERE cp.commission_id = c.id) as programs_count,
               (SELECT COUNT(*) FROM commission_programs cp WHERE cp.commission_id = c.id AND cp.type = 'Competition') as competitions_count
        FROM commissions c 
        ORDER BY c.order_num ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_get_commission(commission_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM commissions WHERE id = ?", (commission_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    res = dict(row)
    cursor.execute("""
        SELECT cp.*, c.name as commission_name,
               (SELECT COUNT(*) FROM program_participants pp WHERE pp.program_id = cp.id) as participants_count
        FROM commission_programs cp 
        JOIN commissions c ON cp.commission_id = c.id
        WHERE cp.commission_id = ?
        ORDER BY cp.start_date DESC
    """, (commission_id,))
    programs = cursor.fetchall()
    res["programs"] = [dict(p) for p in programs]
    conn.close()
    return res

def db_get_programs(commission_id=None, program_type=None, status=None, allowed_parish_ids=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = """
        SELECT cp.*, 
               c.name as commission_name,
               c.icon_name as commission_icon,
               p.name as parish_name,
               (SELECT COUNT(*) FROM program_participants pp WHERE pp.program_id = cp.id) as participants_count
        FROM commission_programs cp
        JOIN commissions c ON cp.commission_id = c.id
        LEFT JOIN parishes p ON cp.parish_id = p.id
        WHERE 1=1
    """
    params = []
    if commission_id:
        sql += " AND cp.commission_id = ?"
        params.append(commission_id)
    if program_type and program_type != "all":
        sql += " AND cp.type = ?"
        params.append(program_type)
    if status and status != "all":
        sql += " AND cp.status = ?"
        params.append(status)
    sql += " ORDER BY cp.start_date ASC"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_get_program(program_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT cp.*, 
               c.name as commission_name,
               c.icon_name as commission_icon,
               c.director_name as commission_director,
               p.name as parish_name
        FROM commission_programs cp
        JOIN commissions c ON cp.commission_id = c.id
        LEFT JOIN parishes p ON cp.parish_id = p.id
        WHERE cp.id = ?
    """, (program_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    res = dict(row)
    cursor.execute("""
        SELECT pp.*, pr.name as parish_name
        FROM program_participants pp
        LEFT JOIN parishes pr ON pp.parish_id = pr.id
        WHERE pp.program_id = ?
        ORDER BY pp.score DESC, pp.registered_at ASC
    """, (program_id,))
    parts = cursor.fetchall()
    res["participants"] = [dict(p) for p in parts]
    conn.close()
    return res

def db_create_program(data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO commission_programs 
        (commission_id, diocese_id, deanery_id, parish_id, title, description, type, target_audience,
         start_date, end_date, venue, registration_deadline, eligibility, guidelines, max_participants,
         contact_person, contact_phone, status, banner_url, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("commission_id"), data.get("diocese_id"), data.get("deanery_id"), data.get("parish_id"),
        data.get("title"), data.get("description"), data.get("type", "Program"), data.get("target_audience", "All"),
        data.get("start_date"), data.get("end_date"), data.get("venue"), data.get("registration_deadline"),
        data.get("eligibility"), data.get("guidelines"), data.get("max_participants"),
        data.get("contact_person"), data.get("contact_phone"), data.get("status", "Upcoming"),
        data.get("banner_url"), data.get("created_by")
    ))
    conn.commit()
    p_id = cursor.lastrowid
    conn.close()
    return p_id

def db_update_program(program_id, data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE commission_programs
        SET commission_id = ?, parish_id = ?, title = ?, description = ?, type = ?, target_audience = ?,
            start_date = ?, end_date = ?, venue = ?, registration_deadline = ?, eligibility = ?,
            guidelines = ?, max_participants = ?, contact_person = ?, contact_phone = ?, status = ?
        WHERE id = ?
    """, (
        data.get("commission_id"), data.get("parish_id"), data.get("title"), data.get("description"),
        data.get("type"), data.get("target_audience"), data.get("start_date"), data.get("end_date"),
        data.get("venue"), data.get("registration_deadline"), data.get("eligibility"),
        data.get("guidelines"), data.get("max_participants"), data.get("contact_person"),
        data.get("contact_phone"), data.get("status"), program_id
    ))
    conn.commit()
    conn.close()
    return True

def db_delete_program(program_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM commission_programs WHERE id = ?", (program_id,))
    conn.commit()
    conn.close()
    return True

def db_get_program_participants(program_id, parish_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = """
        SELECT pp.*, pr.name as parish_name, cp.title as program_title
        FROM program_participants pp
        JOIN commission_programs cp ON pp.program_id = cp.id
        LEFT JOIN parishes pr ON pp.parish_id = pr.id
        WHERE pp.program_id = ?
    """
    params = [program_id]
    if parish_id:
        sql += " AND pp.parish_id = ?"
        params.append(parish_id)
    sql += " ORDER BY pp.score DESC, pp.registered_at ASC"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_get_participant(participant_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pp.*, pr.name as parish_name, cp.title as program_title, cp.venue, cp.start_date,
               c.name as commission_name, c.director_name as commission_director
        FROM program_participants pp
        JOIN commission_programs cp ON pp.program_id = cp.id
        JOIN commissions c ON cp.commission_id = c.id
        LEFT JOIN parishes pr ON pp.parish_id = pr.id
        WHERE pp.id = ?
    """, (participant_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def db_register_participant(data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO program_participants
        (program_id, parish_id, member_id, participant_name, age, gender, contact_phone, contact_email, team_name, category, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("program_id"), data.get("parish_id"), data.get("member_id"), data.get("participant_name"),
        data.get("age"), data.get("gender"), data.get("contact_phone"), data.get("contact_email"),
        data.get("team_name"), data.get("category", "General"), data.get("status", "Registered")
    ))
    conn.commit()
    part_id = cursor.lastrowid
    conn.close()
    return part_id

def db_update_participant(participant_id, data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE program_participants
        SET participant_name = ?, age = ?, gender = ?, contact_phone = ?, contact_email = ?,
            team_name = ?, category = ?, status = ?, score = ?, `rank` = ?, certificate_issued = ?
        WHERE id = ?
    """, (
        data.get("participant_name"), data.get("age"), data.get("gender"), data.get("contact_phone"),
        data.get("contact_email"), data.get("team_name"), data.get("category"), data.get("status"),
        data.get("score"), data.get("rank"), data.get("certificate_issued", 0), participant_id
    ))
    conn.commit()
    conn.close()
    return True

def db_delete_participant(participant_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM program_participants WHERE id = ?", (participant_id,))
    conn.commit()
    conn.close()
    return True

