from app import create_app
from app.extensions import db
from app.models.category import Category


DEFAULT_CATEGORIES = [
    ("Accion represiva del gobierno", "accion-represiva", "Operativos, detenciones y violencia estatal."),
    (
        "Movimiento de tropas",
        "movimiento-tropas",
        "Movimientos policiales, brigada especial o tropas. Indica fecha y hora del movimiento y describe tipo de tropas, armamento o motivo.",
    ),
    ("Residencia de represor", "residencia-represor", "Direcciones o zonas asociadas a represores."),
    ("Centro Penitenciario", "centro-penitenciario", "Carceles y centros de detencion."),
    ("Estacion de Policia", "estacion-policia", "Unidades policiales y puestos."),
    ("Escuela del Partido Comunista", "escuela-pcc", "Instituciones de formacion del PCC."),
    ("Sede del Partido Comunista", "sede-pcc", "Sedes provinciales o municipales del PCC."),
    ("Sede de la Seguridad del Estado", "sede-seguridad-estado", "Instalaciones de la Seguridad del Estado."),
    ("Unidad militar", "unidad-militar", "Bases y unidades militares."),
    ("Base de espionaje", "base-espionaje", "Infraestructura de inteligencia o espionaje."),
    ("Otros", "otros", "Reportes generales o difíciles de clasificar."),
]


def main():
    app = create_app()
    with app.app_context():
        for name, slug, description in DEFAULT_CATEGORIES:
            exists = Category.query.filter_by(slug=slug).first()
            if not exists:
                db.session.add(Category(name=name, slug=slug, description=description))
        db.session.commit()
        print("Categorias cargadas.")


if __name__ == "__main__":
    main()
