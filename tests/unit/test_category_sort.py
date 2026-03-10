from unittest.mock import MagicMock
from app.services.category_sort import sort_categories_for_forms


def _cat(slug, name):
    c = MagicMock()
    c.slug = slug
    c.name = name
    return c


class TestSortCategoriesForForms:
    def test_priority_order(self):
        cats = [
            _cat("otros", "Otros"),
            _cat("desconexion-internet", "Desconexión"),
            _cat("accion-represiva", "Acción represiva"),
            _cat("movimiento-tropas", "Movimiento de tropas"),
            _cat("generico", "Genérico"),
        ]
        result = sort_categories_for_forms(cats)
        slugs = [c.slug for c in result]
        assert slugs[0] == "accion-represiva"
        assert slugs[1] == "movimiento-tropas"
        assert slugs[2] == "desconexion-internet"
        assert slugs[-1] == "otros"

    def test_empty(self):
        assert sort_categories_for_forms([]) == []
