from database import get_db_connection

def migrate():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Check if member_id exists in family_relations
        cursor.execute("SHOW COLUMNS FROM family_relations LIKE 'member_id'")
        result = cursor.fetchone()
        if not result:
            print("Adding member_id to family_relations table...")
            cursor.execute("ALTER TABLE family_relations ADD COLUMN member_id INT")
            
            # Optionally add a foreign key if needed
            try:
                cursor.execute("ALTER TABLE family_relations ADD CONSTRAINT fk_fr_member FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE SET NULL")
            except Exception as e:
                print(f"Warning: Could not add foreign key: {e}")
        else:
            print("member_id already exists.")
            
        conn.commit()
        print("Migration successful.")
    except Exception as e:
        print(f"Error during migration: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
