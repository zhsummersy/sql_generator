from flask import Flask, request, jsonify, render_template
import sqlite3
import json
import os
from datetime import datetime

app = Flask(__name__)

# 数据库配置
DATABASE = 'database_designer.db'
DESIGN_DB = 'design_storage.db'

def get_db_connection(db_file=DATABASE):
    """获取数据库连接"""
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    return conn

def init_databases():
    """初始化数据库"""
    # 初始化设计存储数据库
    conn = get_db_connection(DESIGN_DB)
    c = conn.cursor()
    
    # 创建设计项目表
    c.execute('''
        CREATE TABLE IF NOT EXISTS design_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建表设计表
    c.execute('''
        CREATE TABLE IF NOT EXISTS table_designs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            table_name TEXT NOT NULL,
            table_comment TEXT,
            design_data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES design_projects (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def create_actual_table(table_design):
    """根据设计创建实际的数据库表"""
    try:
        conn = get_db_connection(DATABASE)
        c = conn.cursor()
        
        table_name = table_design['name']
        
        # 检查表是否已存在
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if c.fetchone():
            # 表已存在，先删除
            c.execute(f"DROP TABLE {table_name}")
        
        # 构建创建表的SQL
        sql = f"CREATE TABLE {table_name} ("
        
        fields_sql = []
        primary_keys = []
        
        for field in table_design['fields']:
            field_sql = f"{field['name']} {field['type']}"
            
            # 添加长度限制
            if field.get('length'):
                field_sql += f"({field['length']})"
            
            # 添加非空约束
            if not field.get('nullable', True):
                field_sql += " NOT NULL"
            
            # 添加唯一约束
            if field.get('unique'):
                field_sql += " UNIQUE"
            
            # 添加默认值
            if field.get('default'):
                field_sql += f" DEFAULT {field['default']}"
            
            fields_sql.append(field_sql)
            
            # 记录主键字段
            if field.get('primary'):
                primary_keys.append(field['name'])
        
        # 添加主键约束
        if primary_keys:
            fields_sql.append(f"PRIMARY KEY ({', '.join(primary_keys)})")
        
        sql += ", ".join(fields_sql)
        sql += ")"
        
        # 执行创建表
        c.execute(sql)
        
        # 添加表注释（SQLite不支持表注释，这里记录到设计表中）
        if table_design.get('comment'):
            save_table_comment(table_name, table_design['comment'])
        
        conn.commit()
        conn.close()
        
        return True, f"表 {table_name} 创建成功"
        
    except Exception as e:
        return False, f"创建表失败: {str(e)}"

def save_table_comment(table_name, comment):
    """保存表注释到设计表"""
    try:
        conn = get_db_connection(DESIGN_DB)
        c = conn.cursor()
        
        c.execute('''
            INSERT OR REPLACE INTO table_comments (table_name, comment)
            VALUES (?, ?)
        ''', (table_name, comment))
        
        conn.commit()
        conn.close()
    except:
        # 如果表不存在，忽略错误
        pass

def get_table_structure(table_name):
    """获取表结构信息"""
    try:
        conn = get_db_connection(DATABASE)
        c = conn.cursor()
        
        # 获取表信息
        c.execute(f"PRAGMA table_info({table_name})")
        columns = c.fetchall()
        
        # 获取索引信息（主键、唯一约束）
        c.execute(f"PRAGMA index_list({table_name})")
        indexes = c.fetchall()
        
        table_info = {
            'name': table_name,
            'columns': [],
            'primary_keys': [],
            'unique_constraints': []
        }
        
        for col in columns:
            column_info = {
                'name': col[1],
                'type': col[2],
                'nullable': not col[3],
                'default_value': col[4],
                'primary_key': col[5] == 1
            }
            table_info['columns'].append(column_info)
            
            if column_info['primary_key']:
                table_info['primary_keys'].append(column_info['name'])
        
        conn.close()
        return table_info
        
    except Exception as e:
        return None

@app.route('/')
def index():
    """首页"""
    return render_template('index.html')

# API路由 - 创建新表
@app.route('/api/tables', methods=['POST'])
def create_table():
    """根据设计创建新表"""
    try:
        data = request.json
        table_design = data.get('table')
        
        if not table_design or not table_design.get('name'):
            return jsonify({'success': False, 'error': '表设计数据不完整'}), 400
        
        # 创建实际的数据表
        success, message = create_actual_table(table_design)
        
        if success:
            # 保存设计到设计数据库
            save_table_design(table_design)
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'error': message}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def save_table_design(table_design):
    """保存表设计到设计数据库"""
    try:
        conn = get_db_connection(DESIGN_DB)
        c = conn.cursor()
        
        # 创建表设计表（如果不存在）
        c.execute('''
            CREATE TABLE IF NOT EXISTS table_designs_simple (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT UNIQUE NOT NULL,
                design_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 插入或更新设计数据
        c.execute('''
            INSERT OR REPLACE INTO table_designs_simple (table_name, design_data, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (table_design['name'], json.dumps(table_design, ensure_ascii=False)))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"保存设计数据失败: {e}")

# API路由 - 更新表结构
@app.route('/api/tables/<table_name>', methods=['PUT'])
def update_table(table_name):
    """更新表结构"""
    try:
        data = request.json
        table_design = data.get('table')
        
        if not table_design:
            return jsonify({'success': False, 'error': '表设计数据不能为空'}), 400
        
        # 检查表是否存在
        conn = get_db_connection(DATABASE)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': f'表 {table_name} 不存在'}), 404
        conn.close()
        
        # 由于SQLite的ALTER TABLE功能有限，这里采用删除重建的方式
        # 在实际生产环境中，应该使用更复杂的迁移策略
        
        # 备份数据（这里简化处理，实际应该备份数据）
        success, message = create_actual_table(table_design)
        
        if success:
            # 更新设计数据
            save_table_design(table_design)
            return jsonify({'success': True, 'message': f'表 {table_name} 更新成功'})
        else:
            return jsonify({'success': False, 'error': message}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# API路由 - 删除表
@app.route('/api/tables/<table_name>', methods=['DELETE'])
def delete_table(table_name):
    """删除表"""
    try:
        conn = get_db_connection(DATABASE)
        c = conn.cursor()
        
        # 检查表是否存在
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': f'表 {table_name} 不存在'}), 404
        
        # 删除表
        c.execute(f"DROP TABLE {table_name}")
        
        # 删除设计数据
        conn_design = get_db_connection(DESIGN_DB)
        c_design = conn_design.cursor()
        c_design.execute("DELETE FROM table_designs_simple WHERE table_name=?", (table_name,))
        conn_design.commit()
        conn_design.close()
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': f'表 {table_name} 删除成功'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# API路由 - 获取所有表
@app.route('/api/tables', methods=['GET'])
def get_all_tables():
    """获取所有表信息"""
    try:
        conn = get_db_connection(DATABASE)
        c = conn.cursor()
        
        # 获取所有表名
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = c.fetchall()
        
        table_list = []
        for table in tables:
            table_name = table[0]
            table_info = get_table_structure(table_name)
            if table_info:
                table_list.append(table_info)
        
        conn.close()
        return jsonify({'success': True, 'tables': table_list})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# API路由 - 获取表详情
@app.route('/api/tables/<table_name>', methods=['GET'])
def get_table_detail(table_name):
    """获取表详细结构"""
    try:
        table_info = get_table_structure(table_name)
        if not table_info:
            return jsonify({'success': False, 'error': f'表 {table_name} 不存在'}), 404
        
        # 获取设计数据
        conn = get_db_connection(DESIGN_DB)
        c = conn.cursor()
        c.execute("SELECT design_data FROM table_designs_simple WHERE table_name=?", (table_name,))
        design_row = c.fetchone()
        conn.close()
        
        design_data = None
        if design_row:
            design_data = json.loads(design_row[0])
        
        return jsonify({
            'success': True, 
            'table': table_info,
            'design': design_data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# API路由 - 添加字段
@app.route('/api/tables/<table_name>/fields', methods=['POST'])
def add_field(table_name):
    """向表中添加字段"""
    try:
        data = request.json
        field_design = data.get('field')
        
        if not field_design or not field_design.get('name'):
            return jsonify({'success': False, 'error': '字段数据不完整'}), 400
        
        # 检查表是否存在
        conn = get_db_connection(DATABASE)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        if not c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': f'表 {table_name} 不存在'}), 404
        
        # 构建添加字段的SQL
        field_sql = f"ALTER TABLE {table_name} ADD COLUMN {field_design['name']} {field_design['type']}"
        
        if field_design.get('length'):
            field_sql += f"({field_design['length']})"
        
        if not field_design.get('nullable', True):
            field_sql += " NOT NULL"
        
        if field_design.get('unique'):
            field_sql += " UNIQUE"
        
        if field_design.get('default'):
            field_sql += f" DEFAULT {field_design['default']}"
        
        # 执行添加字段
        c.execute(field_sql)
        
        conn.commit()
        conn.close()
        
        # 更新设计数据
        update_design_after_field_change(table_name, 'add', field_design)
        
        return jsonify({'success': True, 'message': f'字段 {field_design["name"]} 添加成功'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def update_design_after_field_change(table_name, operation, field_data):
    """在字段变更后更新设计数据"""
    try:
        conn = get_db_connection(DESIGN_DB)
        c = conn.cursor()
        
        c.execute("SELECT design_data FROM table_designs_simple WHERE table_name=?", (table_name,))
        design_row = c.fetchone()
        
        if design_row:
            design_data = json.loads(design_row[0])
            
            if operation == 'add':
                design_data['fields'].append(field_data)
            elif operation == 'delete':
                design_data['fields'] = [f for f in design_data['fields'] if f['name'] != field_data['name']]
            elif operation == 'update':
                for i, field in enumerate(design_data['fields']):
                    if field['name'] == field_data['old_name']:
                        design_data['fields'][i] = field_data
                        break
            
            # 更新设计数据
            c.execute('''
                UPDATE table_designs_simple 
                SET design_data = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE table_name = ?
            ''', (json.dumps(design_data, ensure_ascii=False), table_name))
            
            conn.commit()
        
        conn.close()
    except Exception as e:
        print(f"更新设计数据失败: {e}")

# API路由 - 删除字段
@app.route('/api/tables/<table_name>/fields/<field_name>', methods=['DELETE'])
def delete_field(table_name, field_name):
    """删除表中的字段"""
    try:
        # SQLite不支持直接删除字段，这里采用重建表的方式
        # 获取原表设计
        conn_design = get_db_connection(DESIGN_DB)
        c_design = conn_design.cursor()
        c_design.execute("SELECT design_data FROM table_designs_simple WHERE table_name=?", (table_name,))
        design_row = c_design.fetchone()
        conn_design.close()
        
        if not design_row:
            return jsonify({'success': False, 'error': '找不到表设计数据'}), 404
        
        design_data = json.loads(design_row[0])
        
        # 从设计中移除字段
        design_data['fields'] = [f for f in design_data['fields'] if f['name'] != field_name]
        
        # 重建表
        success, message = create_actual_table(design_data)
        
        if success:
            return jsonify({'success': True, 'message': f'字段 {field_name} 删除成功'})
        else:
            return jsonify({'success': False, 'error': message}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# API路由 - 更新字段
@app.route('/api/tables/<table_name>/fields/<field_name>', methods=['PUT'])
def update_field(table_name, field_name):
    """更新字段定义"""
    try:
        data = request.json
        new_field_data = data.get('field')
        
        if not new_field_data:
            return jsonify({'success': False, 'error': '字段数据不能为空'}), 400
        
        # 获取原表设计
        conn_design = get_db_connection(DESIGN_DB)
        c_design = conn_design.cursor()
        c_design.execute("SELECT design_data FROM table_designs_simple WHERE table_name=?", (table_name,))
        design_row = c_design.fetchone()
        conn_design.close()
        
        if not design_row:
            return jsonify({'success': False, 'error': '找不到表设计数据'}), 404
        
        design_data = json.loads(design_row[0])
        
        # 更新设计中的字段
        field_updated = False
        for i, field in enumerate(design_data['fields']):
            if field['name'] == field_name:
                new_field_data['old_name'] = field_name  # 记录原字段名
                design_data['fields'][i] = new_field_data
                field_updated = True
                break
        
        if not field_updated:
            return jsonify({'success': False, 'error': f'字段 {field_name} 不存在'}), 404
        
        # 重建表
        success, message = create_actual_table(design_data)
        
        if success:
            return jsonify({'success': True, 'message': f'字段 {field_name} 更新成功'})
        else:
            return jsonify({'success': False, 'error': message}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# API路由 - 执行自定义SQL
@app.route('/api/execute-sql', methods=['POST'])
def execute_sql():
    """执行自定义SQL语句"""
    try:
        data = request.json
        sql = data.get('sql')
        
        if not sql:
            return jsonify({'success': False, 'error': 'SQL语句不能为空'}), 400
        
        conn = get_db_connection(DATABASE)
        c = conn.cursor()
        
        # 执行SQL
        c.execute(sql)
        
        # 如果是查询语句，返回结果
        if sql.strip().upper().startswith('SELECT'):
            results = c.fetchall()
            columns = [description[0] for description in c.description]
            
            formatted_results = []
            for row in results:
                formatted_row = {}
                for i, value in enumerate(row):
                    formatted_row[columns[i]] = value
                formatted_results.append(formatted_row)
            
            conn.close()
            return jsonify({'success': True, 'results': formatted_results, 'columns': columns})
        else:
            # 对于非查询语句，返回影响的行数
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'SQL执行成功', 'rows_affected': c.rowcount})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# API路由 - 获取数据库状态
@app.route('/api/database-status', methods=['GET'])
def get_database_status():
    """获取数据库状态信息"""
    try:
        conn = get_db_connection(DATABASE)
        c = conn.cursor()
        
        # 获取所有表
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [table[0] for table in c.fetchall()]
        
        # 获取数据库大小
        db_file = os.path.getsize(DATABASE)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'tables_count': len(tables),
            'tables': tables,
            'database_size': db_file,
            'last_updated': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    init_databases()
    print("数据库初始化完成")
    print("API服务启动在 http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)