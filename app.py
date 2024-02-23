from flask import Flask, request,flash, render_template_string,render_template, jsonify,redirect, url_for,send_file,session, Response
from crewai import Agent, Task, Crew, Process
import mysql.connector
from mysql.connector import Error
import secrets
import os
from io import BytesIO
import zipfile
import base64

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'crew2'
}

def create_connection():
    connection = None
    try:
        connection = mysql.connector.connect(**db_config)
    except Error as e:
        flash(f"Error: '{e}'")
    return connection

def create_users_table():
    conn = create_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                openai_api_key VARCHAR(255) UNIQUE
            )
        """)
        conn.commit()
    except Error as e:
        flash(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()

def create_agents_table():
    conn = create_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                role VARCHAR(255) NOT NULL,
                goal TEXT NOT NULL,
                verbose BOOLEAN NOT NULL,
                backstory TEXT NOT NULL,
                allow_delegation BOOLEAN NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.commit()
    except Error as e:
        flash(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()

def create_tasks_table():
    conn = create_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                agent_id INT,
                task_name VARCHAR(255) NOT NULL,
                task_description TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            )
        """)
        conn.commit()
    except Error as e:
        flash(f"Error: {e}")
    finally:
        cursor.close()
        conn.close()

def create_task_results_table():
    conn = create_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_results (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT,
                task_id INT,
                result LONGTEXT,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        """)
        conn.commit()
    except Error as e:
        flash(f"Error creating task_results table: {e}")
    finally:
        cursor.close()
        conn.close()

@app.route('/')
def index():
    agents = []
    tasks = []

    if 'user_id' in session:
        user_id = session['user_id']
        conn = create_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT id, role FROM agents WHERE user_id = %s", (user_id,))
            agents = cursor.fetchall()
            cursor.execute("SELECT id, task_name, task_description, agent_id FROM tasks WHERE user_id = %s", (user_id,))
            tasks = cursor.fetchall()
        except Error as e:
            flash(f"Error: {e}")
        finally:
            cursor.close()
            conn.close()

    return render_template('api_key_form.html', agents=agents, tasks=tasks)




@app.route('/set_api_key', methods=['GET', 'POST'])
def set_api_key():
    if request.method == 'POST':
        openai_api_key = request.form['openai_api_key']
        conn = create_connection()
        cursor = conn.cursor(buffered=True)
        try:
            cursor.execute("SELECT id FROM users WHERE openai_api_key = %s", (openai_api_key,))
            user = cursor.fetchone()
            if user:
                session['user_id'] = user[0]  # Storing user ID in session
                session['openai_api_key'] = openai_api_key  # Store API key in session

                flash('Login success!', 'success')
            else:
                cursor.execute("INSERT INTO users (openai_api_key) VALUES (%s)", (openai_api_key,))
                conn.commit()
                cursor.execute("SELECT id FROM users WHERE openai_api_key = %s", (openai_api_key,))
                user = cursor.fetchone()
                session['user_id'] = user[0]  # Storing new user ID in session
                session['openai_api_key'] = openai_api_key  # Store API key in session

                flash('API Key set successfully!', 'success')
        except Error as e:
            flash(f'Error: {str(e)}', 'error')
        finally:
            cursor.close()
            conn.close()
        return redirect(url_for('index'))
    # If the request method is GET, redirect to index
    return redirect(url_for('index'))



@app.route('/create_agent', methods=['POST'])
def create_agent():
    # Check if user_id is stored in session
    if 'user_id' in session:
        user_id = session['user_id']  # Retrieve user ID from session
        role = request.form['role']
        goal = request.form['goal']
        verbose = request.form['verbose'] == 'true'
        backstory = request.form['backstory']
        allow_delegation = request.form['allow_delegation'] == 'true'

        conn = create_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO agents (user_id, role, goal, verbose, backstory, allow_delegation) VALUES (%s, %s, %s, %s, %s, %s)",
                           (user_id, role, goal, verbose, backstory, allow_delegation))
            conn.commit()
            flash('Agent created successfully!', 'success')
        except Error as e:
            flash(f'Error creating agent: {str(e)}', 'error')
        finally:
            cursor.close()
            conn.close()
    else:
        flash('You must be logged in to create an agent.', 'error')

    return redirect(url_for('index'))

@app.route('/create_task', methods=['POST'])
def create_task():
    if 'user_id' in session:
        user_id = session['user_id']
        agent_id = request.form['selected_agent']
        task_name = request.form['task_name']
        task_description = request.form['task_description']
        # flash(user_id,agent_id,task_description,task_name)
        conn = create_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO tasks (user_id, agent_id, task_name, task_description) VALUES (%s, %s, %s, %s)",
                           (user_id, agent_id, task_name, task_description))
            conn.commit()
            flash('Task added successfully!', 'success')
        except Error as e:
            flash(f'Error adding task: {str(e)}', 'error')
        finally:
            cursor.close()
            conn.close()
    else:
        flash('You must be logged in to create a task.', 'error')

    return redirect(url_for('index'))


@app.route('/delete_task', methods=['POST'])
def delete_task():
    if 'user_id' in session:
        task_id = request.form['task_id']
        flash(task_id,"task_id")
        conn = create_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
            conn.commit()
            flash('Task deleted successfully!', 'success')
        except Error as e:
            flash(f'Error deleting task: {str(e)}', 'error')
        finally:
            cursor.close()
            conn.close()
    else:
        flash('You must be logged in to delete a task.', 'error')

    return redirect(url_for('index'))

@app.route('/reassign_task', methods=['POST'])
def reassign_task():
    if 'user_id' in session:
        # Original task data
        task_id = request.form['task_id']
        new_agent_id = request.form['new_agent_id']
        flash(f"Assigning Task ID: {task_id} to Agent ID: {new_agent_id}")  # Debug flash

        conn = create_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            # First, retrieve the original task details
            cursor.execute("SELECT task_name, task_description FROM tasks WHERE id = %s AND user_id = %s", 
                           (task_id, session['user_id']))
            original_task = cursor.fetchone()

            if original_task:
                # Now, insert the new task entry with the retrieved details
                cursor.execute("INSERT INTO tasks (user_id, agent_id, task_name, task_description) VALUES (%s, %s, %s, %s)",
                               (session['user_id'], new_agent_id, original_task['task_name'], original_task['task_description']))
                conn.commit()
                flash('Task assigned successfully!', 'success')
            else:
                flash('Original task not found.', 'error')
        except Error as e:
            flash(f'Error assigning task: {str(e)}', 'error')
        finally:
            cursor.close()
            conn.close()
    else:
        flash('You must be logged in to assign a task.', 'error')

    return redirect(url_for('index'))


# Call this function at the startup of your application
create_users_table()
create_agents_table()
create_tasks_table()
create_task_results_table()

def consolidate_code():
    # Consolidate the code from this script
    with open(__file__, 'r') as file:
        code_content = file.read()
    return code_content

@app.route('/execute_tasks', methods=['POST'])
def execute_tasks():

    if 'user_id' not in session or 'openai_api_key' not in session:
        flash('You must be logged in and have an API key set to execute tasks.', 'error')
        return redirect(url_for('index'))

    selected_task_ids = request.json.get('selected_tasks')

    user_id = session['user_id']
    os.environ['OPENAI_API_KEY'] = session.get('openai_api_key')
    openai_api_key = os.environ['OPENAI_API_KEY']

    with create_connection() as conn:
        with conn.cursor(dictionary=True) as cursor:

            agents = []
            tasks = []
            for task_id in selected_task_ids:
                cursor.execute("SELECT t.task_description, a.role, a.goal, a.verbose, a.backstory, a.allow_delegation FROM tasks t JOIN agents a ON t.agent_id = a.id WHERE t.id = %s AND t.user_id = %s", 
                               (task_id, user_id))
                task_agent_data = cursor.fetchone()
                if task_agent_data:
                    # Pass the API key as a parameter when creating the Agent
                    agent = Agent(role=task_agent_data['role'], goal=task_agent_data['goal'], verbose=task_agent_data['verbose'], backstory=task_agent_data['backstory'], allow_delegation=task_agent_data['allow_delegation'], openai_api_key=openai_api_key)
                    task = Task(description=task_agent_data['task_description'], agent=agent)
                    agents.append(agent)
                    tasks.append(task)

            if not tasks:
                flash('No tasks selected or tasks not found.', 'error')
                return redirect(url_for('index'))

            # Execute tasks and get results
            app_dev_crew = Crew(api_key=openai_api_key, agents=agents, tasks=tasks, process=Process.sequential)
            result = app_dev_crew.kickoff()

            # Create an in-memory BytesIO object for the zip file
            in_memory_zip = BytesIO()
        
    # Create a Zip file
            with zipfile.ZipFile(in_memory_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zipf:
        # Add task results to the zip file
                results_str = f"Result:\n{result}"
                zipf.writestr('task_results.txt', results_str)
        
        # Add execution code to the zip file
                complete_code = consolidate_code()
                zipf.writestr('consolidated_code.py', complete_code)

            # Encode the ZIP file as base64
            in_memory_zip.seek(0)
            encoded_zip = base64.b64encode(in_memory_zip.read()).decode('utf-8')

            # Return results and encoded zip file as JSON
            return jsonify({'result': result, 'encoded_zip': encoded_zip})





if __name__ == '__main__':
    app.run(debug=True, port=3244)  # Set debug=False in production

