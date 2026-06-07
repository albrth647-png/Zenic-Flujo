#!/usr/bin/env python3
"""
Workflow Determinista — Generar License Key
Uso: python scripts/generate_license_key.py --type individual --client "Cliente Demo"
"""
import argparse
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.license.generator import LicenseGenerator

def main():
    parser = argparse.ArgumentParser(description='Generar License Key para Workflow Determinista')
    parser.add_argument('--type', choices=['individual', 'reseller', 'enterprise'],
                       default='individual', help='Tipo de licencia')
    parser.add_argument('--client', default='', help='Nombre del cliente')
    parser.add_argument('--days', type=int, default=365, help='Días de validez')
    args = parser.parse_args()
    gen = LicenseGenerator()
    key = gen.generate(args.type, args.client, args.days)
    print(f"\n⚙️  License Key Generada")
    print(f"{'='*40}")
    print(f"  {key}")
    print(f"{'='*40}")
    print(f"  Tipo:     {args.type}")
    print(f"  Cliente:  {args.client or '(sin especificar)'}")
    print(f"  Validez:  {args.days} días")
    print()

if __name__ == '__main__':
    main()
