# DomoLink-Tado 🔥

Intégration Home Assistant sur-mesure et pérenne pour vos équipements de chauffage Tado.

## ✨ Caractéristiques
- **Connexion pérenne (OAuth2 Device Flow)** : Zéro déconnexion au redémarrage, tokens stockés et rafraîchis en dur sur le disque.
- **Tolérance au démarrage (`ConfigEntryNotReady`)** : Aucun blocage en cas de délai réseau.
- **Découverte automatique** de toutes les têtes thermostatiques, thermostats muraux, sondes et relais chaudière.
- **Tableau de bord tactile interactif** :
  - Tuile 4 quadrants globale (`OFF`, `BOOST`, `PROG`, `EXTÉRIEUR`).
  - Grille des pièces avec cadrans et états en direct.
  - Modale tactile haute résolution avec jauge verticale graduée, affichage géant de la consigne et adaptation dynamique de la couleur de fond (Vert ➔ Ambre/Orange ➔ Rouge).
  - Contrôle rapide `OFF`, `AUTO`, `ON`, affichage de la puissance et verrouillage sécurité enfant.
  - Easter Egg cyberpunk **SOCRATE RULES** (triple-clic sur le titre).
- **Mises à jour automatiques** : Détection et installation des releases en 1 clic avec badge dans la barre latérale.

## 📦 Installation
1. Copiez le dossier `custom_components/domolink_tado` dans votre dossier `config/custom_components/`.
2. Redémarrez Home Assistant.
3. Allez dans **Paramètres** -> **Appareils et services** -> **Ajouter une intégration** -> **DomoLink-Tado**.
4. Suivez les instructions affichées pour lier votre compte Tado.
