"""
ERP de consola de juguete. Sirve para dos cosas:

  1. Verificar que el arnes (driver + tools + Pester) funciona antes de
     apuntarlo a tu ERP real.
  2. Probar el agente end-to-end sin riesgo.

Tiene bugs plantados a proposito: el pedido no valida stock, y el total
aplica mal el descuento. Un auditor que funcione deberia encontrarlos.

    python -m auditor.run doctor --config examples/config.demo.yaml
"""
import sys

STOCK = {"P1": 10, "P2": 0}
PRECIOS = {"P1": 100.0, "P2": 250.0}
CLIENTES = {"C1": {"nombre": "Distribuidora Sur", "saldo": 0.0, "limite": 5000.0}}


def out(text=""):
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def prompt(text):
    sys.stdout.write(text)
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return line.strip()


def menu():
    out()
    out("=== ERP DEMO v0.1 ===")
    out("1) Consultar stock")
    out("2) Nuevo pedido")
    out("3) Ver cliente")
    out("0) Salir")


def consultar_stock():
    out()
    for cod, cant in STOCK.items():
        out(f"  {cod}  precio {PRECIOS[cod]:>8.2f}   stock {cant}")


def nuevo_pedido():
    cli = prompt("Cliente: ")
    if cli not in CLIENTES:
        out("ERROR: cliente inexistente")
        return
    cod = prompt("Producto: ")
    if cod not in STOCK:
        out("ERROR: producto inexistente")
        return
    try:
        cant = int(prompt("Cantidad: "))
    except ValueError:
        out("ERROR: cantidad invalida")
        return
    desc = prompt("Descuento %: ") or "0"
    try:
        desc = float(desc)
    except ValueError:
        desc = 0.0

    # BUG PLANTADO 1: no valida stock disponible.
    STOCK[cod] -= cant
    # BUG PLANTADO 2: el descuento se resta como monto fijo, no como porcentaje.
    total = PRECIOS[cod] * cant - desc
    CLIENTES[cli]["saldo"] += total
    out(f"Pedido registrado. Total {total:.2f}. Stock restante {cod}: {STOCK[cod]}")


def ver_cliente():
    cli = prompt("Cliente: ")
    c = CLIENTES.get(cli)
    if not c:
        out("ERROR: cliente inexistente")
        return
    out(f"  {c['nombre']}  saldo {c['saldo']:.2f}  limite {c['limite']:.2f}")


def main():
    while True:
        menu()
        try:
            op = prompt("Opcion: ")
        except (EOFError, KeyboardInterrupt):
            return
        if op == "1":
            consultar_stock()
        elif op == "2":
            nuevo_pedido()
        elif op == "3":
            ver_cliente()
        elif op == "0":
            out("Hasta luego")
            return
        else:
            out("Opcion invalida")


if __name__ == "__main__":
    main()
