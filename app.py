from flask import Flask, render_template, request, redirect, url_for
import mangadb  # Supondo que você tenha um módulo chamado mangadb para lidar com os dados dos mangás

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin', methods=['GET'])
def admin():
    tags = mangadb.get_tags()
    authors = mangadb.get_authors()
    groups = mangadb.get_groups()
    return render_template('admin.html', tags=tags, authors=authors, groups=groups)

@app.route('/add_manga', methods=['POST'])
def add_manga():
    title = request.form['title']
    description = request.form['description']
    tag_ids = request.form.getlist('tag_ids')
    author_id = request.form['author_id']
    group_id = request.form['group_id']

    mangadb.add_manga(title, description, tag_ids, author_id, group_id)
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)
