# VICTOR Finance — mises à jour Windows

Ce dépôt public est réservé aux paquets de distribution de VICTOR Finance. Le développement et le code source restent dans un dépôt privé.

## État actuel

Le canal est initialisé, mais aucune version n’est encore publiée ici. `channels/stable.json` contient donc `release: null`. Ne pas confondre les artefacts privés de compilation avec une version publique disponible.

## Distribution

Les versions testées seront proposées dans GitHub Releases :

https://github.com/daggoth222/victor-finance-updates/releases

Le téléchargement public ne nécessite aucun compte GitHub. Chaque publication doit fournir le ZIP Windows x64, son empreinte SHA-256 et les notes de version. Le manifeste stable est mis à jour seulement après la mise en ligne et la vérification du paquet correspondant.

Le logiciel vérifie ce canal au lancement (sauf mode hors connexion) et propose une vérification manuelle dans Paramètres. Aucune installation ne s’effectue automatiquement. La première intégration permet le téléchargement vérifié puis l’installation manuelle dans un nouveau dossier. Les données du paquet Windows restent dans le profil Windows, hors du dossier du programme.

## Confidentialité et périmètre

Ne jamais déposer de clés, mots de passe, comptes, journaux privés, bases de données ou historiques utilisateurs dans ce dépôt. Les paquets publics peuvent être inspectés et ne doivent contenir aucun secret.

Version d’essai en simulation uniquement. Les paquets sont actuellement non signés. L’empreinte vérifie l’intégrité par rapport au manifeste distribué par GitHub ; elle n’est pas une signature indépendante de l’éditeur. Les conditions commerciales et la licence du logiciel restent à définir.
