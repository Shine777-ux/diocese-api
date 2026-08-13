from database import get_db_connection

def migrate():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        print("Creating parish_groups table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS parish_groups (
            id INT AUTO_INCREMENT PRIMARY KEY,
            parish_id INT NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            FOREIGN KEY (parish_id) REFERENCES parishes(id) ON DELETE CASCADE
        );
        """)
        
        print("Creating member_groups table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS member_groups (
            id INT AUTO_INCREMENT PRIMARY KEY,
            member_id INT NOT NULL,
            group_id INT NOT NULL,
            role VARCHAR(255) DEFAULT 'Member',
            FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
            FOREIGN KEY (group_id) REFERENCES parish_groups(id) ON DELETE CASCADE,
            UNIQUE KEY (member_id, group_id)
        );
        """)
        
        conn.commit()
        print("Migration successful.")
    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
