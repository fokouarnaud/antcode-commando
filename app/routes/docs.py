from flask import Blueprint, jsonify

from app.openapi import OPENAPI_SPEC

docs_bp = Blueprint("docs", __name__)

_DOCS_PAGE = """<!doctype html>
<html>
<head>
    <title>AntCode Commando API Reference</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
</head>
<body>
    <script id="api-reference" data-url="/openapi.json"></script>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
</body>
</html>
"""


@docs_bp.route("/openapi.json", methods=["GET"])
def openapi_json():
    return jsonify(OPENAPI_SPEC), 200


@docs_bp.route("/docs", methods=["GET"])
def docs_page():
    return _DOCS_PAGE, 200, {"Content-Type": "text/html; charset=utf-8"}
