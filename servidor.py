import sqlite3
import sys
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)
DB_NAME = "tareas.db"
HOST = "127.0.0.1"
PORT = 5000


def db():
    try:
        # Se conecta a la DB y crea la tabla.
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tareas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    descripcion TEXT NOT NULL,
                    terminada INTEGER NOT NULL DEFAULT 0
                )
            """)
        return True

    except sqlite3.Error as err:
        print(f"Error en la conexión a la base de datos: {err}")
        return False


@app.route("/tareas", methods=["GET"])
def welcome():
    pag = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="utf-8">
        <title>Bienvenida</title>
    </head>
    <body>
        <section>
            <h1>Página de bienvenida</h1>
            <p>Descripcion de los metodos y como usar la api</p>
            <ul>
                <li><a href="/registro">Ir a /registro</a></li>
                <li><a href="/login">Ir a /login</a></li>
            </ul>
        </section>
    </body>
    </html>
    """
    return render_template_string(pag)


@app.route("/api/tareas", methods=["GET"])
def get_tasks():
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            tasks = conn.execute("""
                SELECT *
                FROM tareas
                ORDER BY id
                """).fetchall()

            if not tasks:
                return jsonify({"mensaje": "No hay tareas guardadas."}), 200

            # Se convierte el tipo "sqlite3.Row" https://docs.python.org/3/library/sqlite3.html#sqlite3.Row
            # a diccionario porque sino jsonify no lo puede serializar.
            # https://docs.python.org/3/library/json.html#json.dumps y la tabla de tipos https://docs.python.org/3/library/json.html#py-to-json-table
            tasks_dict = []
            for task in tasks:
                tasks_dict.append(dict(task))

            return jsonify(tasks_dict)

    except sqlite3.Error as err:
        print(f"Error al obtener todas las tareas de la base de datos: {err}")
        return jsonify({"error": "Error al obtener las tareas"}), 500


@app.route("/api/tareas/<int:task_id>", methods=["GET"])
def get_task(task_id):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            task = conn.execute(
                """
                SELECT *
                FROM tareas
                WHERE id = ?
                """,
                (task_id,),
            ).fetchone()

            if task is None:
                return jsonify({"error": f"No existe una tarea con id #{task_id}"}), 404

            return jsonify(dict(task))

    except sqlite3.Error as err:
        print(f"Error al obtener la tarea #{task_id} de la base de datos: {err}")
        return jsonify({"error": "Error al obtener la tarea"}), 500


@app.route("/api/tareas", methods=["POST"])
def create_task():
    data = request.get_json(silent=True) or {}
    description = data.get("descripcion") or ""
    description.strip()
    finished = 1 if data.get("terminada") is True else 0

    if not description:
        return jsonify({"error": "El campo descripcion es obligatorio"}), 400

    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                INSERT INTO tareas (descripcion, terminada)
                VALUES (?, ?)
                """,
                (description, finished),
            )
            new_id = cursor.lastrowid

            task = conn.execute(
                "SELECT * FROM tareas WHERE id = ?", (new_id,)
            ).fetchone()

            return jsonify(dict(task)), 201

    except sqlite3.Error as err:
        print(f"Error al crear la tarea en la base de datos: {err}")
        return jsonify({"error": "Error al crear la tarea"}), 500


if __name__ == "__main__":
    db_on = db()

    if not db_on:
        print("Error durante la conexión a la base de datos")
        sys.exit()

    print(f"Servidor escuchando en el puerto {PORT}")
    app.run(host=HOST, port=PORT, debug=True)
