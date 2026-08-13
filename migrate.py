from database import get_db_connection

def migrate():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Check if family_id exists in members
        cursor.execute("SHOW COLUMNS FROM members LIKE 'family_id'")
        result = cursor.fetchone()
        if not result:
            print("Adding family_id to members table...")
            cursor.execute("ALTER TABLE members ADD COLUMN family_id INT")
            
            # Optionally add a foreign key if needed
            try:
                cursor.execute("ALTER TABLE members ADD CONSTRAINT fk_family FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE SET NULL")
            except Exception as e:
                print(f"Warning: Could not add foreign key: {e}")
        else:
            print("family_id already exists.")
            
        conn.commit()
        print("Migration successful.")
    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
