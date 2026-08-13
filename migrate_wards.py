from database import get_db_connection

def migrate():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Create wards table
        print("Creating wards table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS wards (
            id INT AUTO_INCREMENT PRIMARY KEY,
            parish_id INT NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            FOREIGN KEY (parish_id) REFERENCES parishes(id) ON DELETE CASCADE
        );
        """)
        
        # 2. Add ward_id to families
        cursor.execute("SHOW COLUMNS FROM families LIKE 'ward_id'")
        result = cursor.fetchone()
        if not result:
            print("Adding ward_id to families table...")
            cursor.execute("ALTER TABLE families ADD COLUMN ward_id INT")
            try:
                cursor.execute("ALTER TABLE families ADD CONSTRAINT fk_families_ward FOREIGN KEY (ward_id) REFERENCES wards(id) ON DELETE SET NULL")
            except Exception as e:
                print(f"Warning: Could not add foreign key: {e}")
        else:
            print("ward_id already exists in families.")
            
        conn.commit()
        print("Migration successful.")
    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
