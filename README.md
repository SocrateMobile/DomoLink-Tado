# DomoLink-Tado 🔥

Intégration Home Assistant sur-mesure et pérenne pour vos équipements de chauffage Tado.

## ✨ Caractéristiques
- **Connexion pérenne (OAuth2 Device Flow)** : Zéro déconnexion au redémarrage, tokens stockés et rafraîchis en continu.
- **Tolérance au démarrage (`ConfigEntryNotReady`)** : Aucun blocage en cas de délai réseau.
- **Géolocalisation automatisée gratuite (Auto-Assist Bypass)** : Synchronisation automatique de la présence Tado (Domicile / Absence) avec vos entités `person.*`, `device_tracker.*` ou `zone.home` de Home Assistant, sans abonnement Auto-Assist payant, avec filtre anti-redondance préservant vos quotas d'appels API.
- **Boutons d'action rapide en 1 clic** :
  - *Reprendre programmation partout* (avec filtre no-op n'émettant aucune requête si aucun forçage n'est actif).
  - *Tout éteindre* (mise hors-gel immédiate).
  - *Boost Intelligent partout* et *Boost Intelligent par pièce* (durée et température configurables).
- **Interrupteur Mode Éco Global** : 1 switch pour basculer toute la maison à température économique ou reprendre automatiquement les plannings.
- **Capteurs externes de température & humidité par pièce (Option A)** :
  - Remplacez la mesure des vannes thermostatiques (souvent faussée près du radiateur) par vos sondes Zigbee/Z-Wave/Bluetooth Home Assistant.
  - Calculs physiques (point de rosée, humidité absolue, risque de moisissure) basés sur vos vraies mesures d'ambiance.
- **Auto-calibrage physique des têtes thermostatiques** :
  - Ajustement automatique de l'offset physique des vannes thermostatiques Tado pour synchroniser le matériel sur vos thermomètres de pièce.
  - Moteur anti-battement intelligent (seuil deadband 0.5°C, cooldown 30 min) : zéro gaspillage de piles et respect absolu des quotas API.
- **Surveillance en temps réel des quotas API Tado (Option B)** :
  - Sniffing automatique des en-têtes HTTP RFC 9110 (`RateLimit`, `RateLimit-Policy`, `RateLimit-Reset`) sur chaque réponse.
  - Capteurs dédiés `sensor.tado_api_quota_restant` et `sensor.tado_api_quota_plafond` avec compte à rebours de réinitialisation.
- **Contrôle Climatisation & Pompes à chaleur (Option C)** :
  - Détection automatique et gestion native des zones `AIR_CONDITIONING` (Smart AC Control).
  - Support complet des modes CVC : Froid (`cool`), Chaud (`heat`), Déshumidification (`dry`), Ventilation seule (`fan_only`), Auto (`auto`) et Éteint (`off`).
  - Sélection des vitesses de ventilation (`auto`, `quiet`, `low`, `middle`, `high`) et commande des volets oscillants (`swing`).
- **Calculs physiques locaux 100% hors-ligne (zéro coût API)** :
  - Point de rosée (°C) et Humidité absolue (g/m³).
  - Indice de risque de moisissure (sûr, modéré, élevé, critique).
  - Conseil d'aération intelligent (basé sur le différentiel hygrométrique intérieur / extérieur).
- **Préchauffage adaptatif local (Early Start)** :
  - Apprentissage automatique de la vitesse de montée en température de chaque pièce (°C/h).
  - Anticipation du démarrage de la chauffe pour atteindre la consigne à l'heure exacte (modes Conseiller ou Autonome).
- **Coupure dynamique sur ouverture de fenêtre** :
  - Algorithme de pente thermique pour couper le radiateur dès une chute brutale sans attendre les alertes cloud.
- **Tableau de bord tactile interactif** :
  - Tuile 4 quadrants globale (`OFF`, `BOOST`, `PROG`, `EXTÉRIEUR`).
  - Grille des pièces avec cadrans et états en direct.
  - Modale tactile haute résolution avec jauge verticale graduée, affichage géant de la consigne et adaptation dynamique de la couleur de fond.
  - Contrôle rapide `OFF`, `AUTO`, `ON`, affichage de la puissance et verrouillage sécurité enfant.
- **Mises à jour automatiques** : Détection et installation des releases en 1 clic avec badge dans la barre latérale.

## 📦 Installation
1. Copiez le dossier `custom_components/domolink_tado` dans votre dossier `config/custom_components/`.
2. Redémarrez Home Assistant.
3. Allez dans **Paramètres** -> **Appareils et services** -> **Ajouter une intégration** -> **DomoLink-Tado**.
4. Suivez les instructions affichées pour lier votre compte Tado.
