# 🎮 UO3D Game Client — Godot Engine 4.x

> **The 3D game client and world runtime for the Ultima Online 3D Remake Project.**

---

* [English](#-english)
  * [Overview](#overview)
  * [Quick Start](#quick-start)
  * [In-Game Controls](#in-game-controls)
  * [Terrain Setup & Generating Terrains](#terrain-setup--generating-terrains)
  * [Syncing Community 3D Buildings](#syncing-community-3d-buildings)
* [Português](#-português)
  * [Visão Geral](#visão-geral)
  * [Início Rápido](#início-rápido)
  * [Comandos no Jogo](#comandos-no-jogo)
  * [Configuração e Geração dos Terrenos](#configuração-e-geração-dos-terrenos)
  * [Sincronizando Construções da Comunidade](#sincronizando-construções-da-comunidade)

---

# 🇬🇧 English

## Overview
This repository contains the game client and runtime engine for the UO3D project, built with **Godot Engine 4.x**. It features:
- Continuous seamless terrain chunk streaming with zero loading screens.
- Multi-map switching across all 6 classic maps (Felucca, Trammel, Ilshenar, Malas, Tokuno, Ter Mur).
- Physics collision shapes and real-time surface raycast inspector.
- Dynamic injection support for refined community buildings from `uo3d-community-buildings`.

## Quick Start
1. Install **Godot Engine 4.x** (Standard 64-bit).
2. Open Godot, click **Import**, and select `godot_project/project.godot`.
3. Press **F5** to run the project.

## In-Game Controls
- `W`, `A`, `S`, `D` & Mouse: Free-look spectator movement.
- `Shift`: Boost flight speed.
- `F1` to `F6`: Switch maps on the fly (Felucca, Trammel, Ilshenar, Malas, Tokuno, Ter Mur).
- `M`: Open interactive teleportation hub to jump to major cities (Britain, Trinsic, Moonglow, etc.).
- Left Click: Surface raycast inspector (displays world coordinates `(wx, wy)`, elevation `Z`, and chunk ID).

## Terrain Setup & Generating Terrains
To keep this repository lightweight (<300 MB), pre-generated multi-gigabyte terrain meshes are excluded. You can generate authentic terrain for all 6 maps locally in ~1 minute using:
```bash
python tools/generate_multi_map_terrain.py
```
*(Requires UO `.mul` files in `/opt/hd_jogos/UOC` or your custom path).*

## Syncing Community 3D Buildings
When refined buildings are modeled in the community repository (`uo3d-community-buildings`), sync them into Godot using:
```bash
python tools/update_world_building.py <path_or_building_name>
# or sync all refined buildings:
python tools/update_world_building.py --all
```

---

# 🇧🇷 Português

## Visão Geral
Este repositório contém o cliente de jogo e runtime do projeto UO3D, desenvolvido na **Godot Engine 4.x**. Principais recursos:
- Streaming contínuo de chunks de terreno sem telas de carregamento.
- Alternância dinâmica entre todos os 6 mapas (Felucca, Trammel, Ilshenar, Malas, Tokuno, Ter Mur).
- Colisão física trimesh e inspetor de superfície via Raycast com mira.
- Sistema de injeção dinâmica de construções refinadas pela comunidade.

## Início Rápido
1. Instale a **Godot Engine 4.x** (Standard 64-bit).
2. Abra a Godot, clique em **Import** e selecione `godot_project/project.godot`.
3. Pressione **F5** para rodar o projeto.

## Comandos no Jogo
- `W`, `A`, `S`, `D` e Mouse: Movimentação de câmera livre.
- `Shift`: Acelerar velocidade de voo.
- `F1` a `F6`: Alternar instantaneamente entre os mapas clássicos.
- `M`: Abrir menu seletor para teletransporte direto às cidades.
- Botão Esquerdo do Mouse: Mira/Inspetor com coordenadas mundiais `(wx, wy)` e elevação `Z`.

## Configuração e Geração dos Terrenos
Para manter este repositório leve (<300 MB) e rápido de clonar, os terrenos gerados não são versionados no git. Você pode gerar o terreno dos 6 mapas em 1 minuto executando:
```bash
python tools/generate_multi_map_terrain.py
```

## Sincronizando Construções da Comunidade
Sempre que uma construção for refinada no repositório comunitário (`uo3d-community-buildings`), sincronize-a na Godot com:
```bash
python tools/update_world_building.py <caminho_ou_nome>
# ou sincronizar todos os prédios refinados:
python tools/update_world_building.py --all
```
