import sqlite3
import sys
import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)
DB_NAME = "tareas.db"
HOST = "127.0.0.1"
PORT = 5000
_ph = PasswordHasher()


def db():
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tareas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    descripcion TEXT NOT NULL,
                    terminada INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario TEXT NOT NULL UNIQUE,
                    contrasena_hash TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sesiones (
                    token TEXT PRIMARY KEY,
                    usuario_id INTEGER NOT NULL,
                    FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE
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
            <table>
                <thead>
                    <tr>
                        <th>Método</th>
                        <th>Ruta</th>
                        <th>Descripción</th>
                        <th>Cuerpo / Respuesta</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>GET</td>
                        <td><code>/tareas</code></td>
                        <td>Página HTML de bienvenida con el resumen de la API.</td>
                        <td>HTML</td>
                    </tr>
                    <tr>
                        <td>POST</td>
                        <td><code>/registro</code></td>
                        <td>Registra un usuario nuevo. La contraseña se guarda hasheada.</td>
                        <td><code>{"usuario": "nombre", "contraseña": "1234"}</code></td>
                    </tr>
                    <tr>
                        <td>POST</td>
                        <td><code>/login</code></td>
                        <td>Verifica credenciales y devuelve un token de sesión.</td>
                        <td><code>{"usuario": "nombre", "contraseña": "1234"}</code></td>
                    </tr>
                    <tr>
                        <td>POST</td>
                        <td><code>/logout</code></td>
                        <td>Cierra la sesión actual e invalida el token.</td>
                        <td>Header <code>Authorization: Bearer &lt;token&gt;</code></td>
                    </tr>
                    <tr>
                        <td>GET</td>
                        <td><code>/api/tareas</code></td>
                        <td>Lista todas las tareas.</td>
                        <td>JSON array (o mensaje si está vacío)</td>
                    </tr>
                    <tr>
                        <td>GET</td>
                        <td><code>/api/tareas/&lt;id&gt;</code></td>
                        <td>Devuelve una tarea por su id.</td>
                        <td>JSON object o <code>404</code></td>
                    </tr>
                    <tr>
                        <td>POST</td>
                        <td><code>/api/tareas</code></td>
                        <td>Crea una nueva tarea.</td>
                        <td><code>{"descripcion": "texto", "terminada": false}</code></td>
                    </tr>
                    <tr>
                        <td>PUT</td>
                        <td><code>/api/tareas/&lt;id&gt;</code></td>
                        <td>Actualiza la descripción y/o el estado de una tarea.</td>
                        <td><code>{"descripcion": "nuevo", "terminada": true}</code></td>
                    </tr>
                    <tr>
                        <td>DELETE</td>
                        <td><code>/api/tareas/&lt;id&gt;</code></td>
                        <td>Elimina una tarea por su id.</td>
                        <td>JSON con el mensaje de confirmación</td>
                    </tr>
                </tbody>
            </table>
        </section>
        <br><br><br>
        <footer>El sistema no tiene autorización, solo autenticación.</footer>
    </body>
    </html>
    """
    return render_template_string(pag)


@app.route("/api/tareas", methods=["GET"])
def get_tasks():
    error = valid_login()
    if error:
        return error

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
    error = valid_login()
    if error:
        return error
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
    error = valid_login()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    description = (data.get("descripcion") or "").strip()
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


@app.route("/api/tareas/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    error = valid_login()
    if error:
        return error
    data = request.get_json(silent=True) or {}

    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row

            task = conn.execute(
                "SELECT * FROM tareas WHERE id = ?", (task_id,)
            ).fetchone()

            if task is None:
                return jsonify({"error": f"No existe una tarea con id #{task_id}"}), 404

            description = data.get("descripcion", task["descripcion"])
            if isinstance(description, str):
                description = description.strip()

            if not description:
                return (
                    jsonify({"error": "El campo descripcion no puede quedar vacío"}),
                    400,
                )

            if "terminada" in data:
                finished = 1 if data["terminada"] is True else 0
            else:
                finished = task["terminada"]

            conn.execute(
                """
                UPDATE tareas
                SET descripcion = ?, terminada = ?
                WHERE id = ?
                """,
                (description, finished, task_id),
            )

            task = conn.execute(
                "SELECT * FROM tareas WHERE id = ?", (task_id,)
            ).fetchone()

            return jsonify(dict(task))

    except sqlite3.Error as err:
        print(f"Error al actualizar la tarea #{task_id} en la base de datos: {err}")
        return jsonify({"error": "Error al actualizar la tarea"}), 500


@app.route("/api/tareas/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    error = valid_login()
    if error:
        return error
    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row

            task = conn.execute(
                "SELECT * FROM tareas WHERE id = ?", (task_id,)
            ).fetchone()

            if task is None:
                return jsonify({"error": f"No existe una tarea con id #{task_id}"}), 404

            conn.execute("DELETE FROM tareas WHERE id = ?", (task_id,))

            return (
                jsonify(
                    {
                        "mensaje": f"Tarea #{task_id} eliminada correctamente",
                        "tarea": dict(task),
                    }
                ),
                200,
            )

    except sqlite3.Error as err:
        print(f"Error al eliminar la tarea #{task_id} de la base de datos: {err}")
        return jsonify({"error": "Error al eliminar la tarea"}), 500


@app.route("/registro", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    user = (data.get("usuario") or "").strip()
    password = data.get("contraseña") or ""

    if not user or not password:
        return (
            jsonify({"error": "Los campos 'usuario' y 'contraseña' son obligatorios"}),
            400,
        )

    if len(user) < 3:
        return jsonify({"error": "El usuario debe tener al menos 3 caracteres"}), 400

    if len(password) < 4:
        return jsonify({"error": "La contraseña debe tener al menos 4 caracteres"}), 400

    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute(
                """
                INSERT INTO usuarios (usuario, contrasena_hash)
                VALUES (?, ?)
                """,
                (
                    user,
                    hash_password(password),
                ),
            )
        return (
            jsonify({"mensaje": f"Usuario '{user}' registrado correctamente"}),
            201,
        )

    except sqlite3.IntegrityError:
        return jsonify({"error": f"El usuario '{user}' ya existe"}), 400

    except sqlite3.Error as err:
        print(f"Error al registrar usuario: {err}")
        return jsonify({"error": "Error al registrar el usuario"}), 500


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    user = (data.get("usuario") or "").strip()
    password = data.get("contraseña") or ""

    if not user or not password:
        return (
            jsonify({"error": "Los campos 'usuario' y 'contraseña' son obligatorios"}),
            400,
        )

    try:
        with sqlite3.connect(DB_NAME) as conn:
            conn.row_factory = sqlite3.Row
            user = conn.execute(
                "SELECT * FROM usuarios WHERE usuario = ?",
                (user,),
            ).fetchone()

            if user is None or not check_password(password, user["contrasena_hash"]):
                return jsonify({"error": "Credenciales inválidas"}), 401

            token = secrets.token_hex(32)
            conn.execute(
                """
                INSERT INTO sesiones (token, usuario_id)
                VALUES (?, ?)
                """,
                (token, user["id"]),
            )

        return (
            jsonify(
                {
                    "usuario": user,
                    "token": token,
                }
            ),
            200,
        )

    except sqlite3.Error as err:
        print(f"Error al iniciar sesión: {err}")
        return jsonify({"error": "Error al iniciar sesión"}), 500


@app.route("/logout", methods=["POST"])
def logout():
    header = request.headers.get("Authorization", "")

    if not header.startswith("Bearer "):
        return (
            jsonify({"error": "Falta el header 'Authorization: Bearer <token>'"}),
            400,
        )

    token = header[7:].strip()

    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.execute(
                "DELETE FROM sesiones WHERE token = ?",
                (token,),
            )

            if cursor.rowcount == 0:
                return jsonify({"error": "Token inválido o sesión ya cerrada"}), 404

        return jsonify({"mensaje": "Sesión cerrada correctamente"}), 200

    except sqlite3.Error as err:
        print(f"Error al cerrar sesión: {err}")
        return jsonify({"error": "Error al cerrar sesión"}), 500


def valid_login():
    header = request.headers.get("Authorization", "")

    if not header.startswith("Bearer "):
        return jsonify({"error": "No autenticado."}), 401

    token = header[7:].strip()

    try:
        with sqlite3.connect(DB_NAME) as conn:
            exists = conn.execute(
                "SELECT 1 FROM sesiones WHERE token = ?",
                (token,),
            ).fetchone()
    except sqlite3.Error as err:
        print(f"Error al verificar la sesión: {err}")
        return jsonify({"error": "Error al verificar la sesión"}), 500

    if exists is None:
        return jsonify({"error": "Token inválido o sesión cerrada"}), 401

    return None


def hash_password(password: str) -> str:
    return _ph.hash(password)


def check_password(password: str, saved_hash: str) -> bool:
    try:
        return _ph.verify(saved_hash, password)
    except VerifyMismatchError:
        return False


if __name__ == "__main__":
    db_on = db()

    if not db_on:
        print("Error durante la conexión a la base de datos")
        sys.exit()

    print(f"Servidor escuchando en el puerto {PORT}")
    app.run(host=HOST, port=PORT, debug=True)
