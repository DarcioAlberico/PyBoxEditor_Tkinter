"""
Script de migracao: Renomeia pastas do formato antigo para o novo formato
case-sensitive (upper_X, lower_x, digit_N, sym_NN).
Tambem move arquivos .png soltos para uma pasta '_orphans'.
"""
import os
import shutil

DATA_DIR = "training_data"

def char_to_folder(char):
    if char.isupper():
        return f"upper_{char}"
    elif char.islower():
        return f"lower_{char}"
    elif char.isdigit():
        return f"digit_{char}"
    else:
        return f"sym_{ord(char)}"

def migrate():
    if not os.path.exists(DATA_DIR):
        print("Pasta training_data nao encontrada.")
        return
    
    items = os.listdir(DATA_DIR)
    folders = [d for d in items if os.path.isdir(os.path.join(DATA_DIR, d))]
    loose_files = [f for f in items if os.path.isfile(os.path.join(DATA_DIR, f))]
    
    print(f"Encontradas {len(folders)} pastas e {len(loose_files)} arquivos soltos.\n")
    
    # Mover arquivos soltos para _orphans
    if loose_files:
        orphan_dir = os.path.join(DATA_DIR, "_orphans")
        os.makedirs(orphan_dir, exist_ok=True)
        for f in loose_files:
            src = os.path.join(DATA_DIR, f)
            dst = os.path.join(orphan_dir, f)
            shutil.move(src, dst)
        print(f"Movidos {len(loose_files)} arquivos soltos para _orphans/\n")
    
    # Renomear pastas
    renamed = 0
    skipped = 0
    
    for folder in sorted(folders):
        # Pular pastas ja no formato novo
        if folder.startswith(("upper_", "lower_", "digit_", "sym_", "ASCII_", "_")):
            print(f"  SKIP: {folder}/ (ja no formato novo)")
            skipped += 1
            continue
        
        # Determinar o caractere
        char = folder  # No formato antigo, a pasta = caractere
        
        # Gerar novo nome
        new_name = char_to_folder(char)
        
        old_path = os.path.join(DATA_DIR, folder)
        new_path = os.path.join(DATA_DIR, new_name)
        
        # Se o destino ja existe, mesclar
        if os.path.exists(new_path):
            # Mover todos os arquivos para a pasta existente
            for f in os.listdir(old_path):
                src = os.path.join(old_path, f)
                dst = os.path.join(new_path, f)
                if os.path.isfile(src):
                    shutil.move(src, dst)
            os.rmdir(old_path)
            print(f"  MERGE: {folder}/ -> {new_name}/ (mesclado)")
        else:
            os.rename(old_path, new_path)
            print(f"  RENAME: {folder}/ -> {new_name}/")
        
        renamed += 1
    
    print(f"\nMigracao concluida! {renamed} pastas migradas, {skipped} ja estavam ok.")
    
    # Mostrar resultado final
    print("\nEstrutura final:")
    for d in sorted(os.listdir(DATA_DIR)):
        if os.path.isdir(os.path.join(DATA_DIR, d)):
            count = len([f for f in os.listdir(os.path.join(DATA_DIR, d)) if f.endswith('.png')])
            print(f"  {d}/ ({count} imagens)")

if __name__ == "__main__":
    migrate()
