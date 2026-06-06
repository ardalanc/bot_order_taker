# DDL

import mysql.connector
from config import database_config,DB_NAME


def drop_n_create_database():
    conn = mysql.connector.connect(**database_config)
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {DB_NAME};")
    cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME};")
    conn.commit()
    cur.close()
    conn.close()
    print(f'database {DB_NAME} created successfully')

def create_table_user():
    conn = mysql.connector.connect(**database_config, database=DB_NAME)
    cur = conn.cursor()
    SQL_Query = """
    CREATE TABLE users (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    chat_id    BIGINT UNIQUE NOT NULL,  -- تلگرام
    name       VARCHAR(100),
    phone      VARCHAR(20),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""
    cur.execute(SQL_Query)
    conn.commit()
    cur.close()
    conn.close()
    print(f'table user created successfully')

def create_table_model():
    conn = mysql.connector.connect(**database_config, database=DB_NAME)
    cur = conn.cursor()
    SQL_Query = """
    CREATE TABLE models (
    id   INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL
    );


    """
    cur.execute(SQL_Query)
    conn.commit()
    cur.close()
    conn.close()
    print(f'table user created successfully')

def create_table_model_items():
    conn = mysql.connector.connect(**database_config, database=DB_NAME)
    cur = conn.cursor()
    SQL_Query = """
    CREATE TABLE model_items (
    id       INT AUTO_INCREMENT PRIMARY KEY,
    model_id INT NOT NULL,
    name     VARCHAR(100) NOT NULL,
    price    DECIMAL(12,0) NOT NULL,
    FOREIGN KEY (model_id) REFERENCES models(id)
);


    """
    cur.execute(SQL_Query)
    conn.commit()
    cur.close()
    conn.close()
    print(f'table user created successfully')

def create_table_orders():
    conn = mysql.connector.connect(**database_config, database=DB_NAME)
    cur = conn.cursor()
    SQL_Query = """
    CREATE TABLE orders (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    status     ENUM('pending','confirmed','in_progress','delivered','cancelled') DEFAULT 'pending',
    notes      TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);



    """
    cur.execute(SQL_Query)
    conn.commit()
    cur.close()
    conn.close()
    print(f'table user created successfully')

def create_table_order_files():
    conn = mysql.connector.connect(**database_config, database=DB_NAME)
    cur = conn.cursor()
    SQL_Query = """
    CREATE TABLE order_files (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    order_id   INT NOT NULL,
    file_id    VARCHAR(200) NOT NULL,  -- file_id تلگرام
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);



    """
    cur.execute(SQL_Query)
    conn.commit()
    cur.close()
    conn.close()
    print(f'table user created successfully')

def create_table_order_items():
    conn = mysql.connector.connect(**database_config, database=DB_NAME)
    cur = conn.cursor()
    SQL_Query = """
    CREATE TABLE order_items (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    order_id       INT NOT NULL,
    model_item_id  INT NOT NULL,
    quantity       INT DEFAULT 1,
    unit_price     DECIMAL(12,0) NOT NULL,  -- قیمت لحظه ثبت
    hand_side      ENUM('left','right','none') DEFAULT 'none',  -- دسته چپ/راست
    FOREIGN KEY (order_id)      REFERENCES orders(id),
    FOREIGN KEY (model_item_id) REFERENCES model_items(id)
);



    """
    cur.execute(SQL_Query)
    conn.commit()
    cur.close()
    conn.close()
    print(f'table user created successfully')






if __name__ == "__main__":
    drop_n_create_database()
    create_table_user()
    
