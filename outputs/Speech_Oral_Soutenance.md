# Speech Oral — Soutenance P10 DSML
# NBA Analyst AI — Système hybride RAG + SQL
# Durée : 15 min présentation + 10 min discussion

---

> **CONSEILS DE LECTURE**
> - Les passages entre [ ] sont des **indications de timing ou de gestes**
> - Les passages en *italique* sont des **transitions naturelles**
> - Parler à un rythme calme — environ 130 mots/minute
> - Regarder l'évaluateur, pas l'écran
> - Pointer les éléments clés sur les slides avec la main, pas avec le curseur uniquement

---

## SLIDE 1 — COUVERTURE
### ⏱ 30 secondes

Bonjour.

Je vais vous présenter aujourd'hui mon projet de fin de formation : **NBA Analyst AI**, un assistant intelligent pour l'analyse de statistiques de basketball.

L'idée centrale est simple : permettre à n'importe qui de poser des questions sur la saison NBA en langage naturel — et obtenir une réponse fiable, sourcée, en quelques secondes.

*[Passer à la slide 2]*

---

## SLIDE 2 — PLAN
### ⏱ 30 secondes

La soutenance se déroule en deux parties.

La **première partie**, qui dure quinze minutes, est consacrée aux livrables : je vais vous montrer comment le système fonctionne, de l'ingestion des données jusqu'à l'évaluation des performances.

La **deuxième partie** est une discussion de dix minutes où j'attends vos questions sur les résultats, les choix techniques, et la façon dont ce système pourrait être utilisé en production.

*[Passer à la slide 3]*

---

## SLIDE 3 — CONTEXTE & OBJECTIFS
### ⏱ 1 minute

**Le problème de départ.**

Les données NBA sont riches mais dispersées. D'un côté, un fichier Excel avec cinq cent soixante-neuf joueurs et trente-neuf colonnes de statistiques. De l'autre, des discussions Reddit en PDF — des analyses qualitatives, des débats sur les joueurs. Ces deux sources sont complémentaires, mais elles ne s'interrogent pas facilement en langage naturel.

**L'objectif du projet** est de construire un assistant IA hybride qui sache répondre à trois types de questions :

Les questions **chiffrées** — par exemple, *"Qui a le plus de points cette saison ?"* — qui nécessitent une requête SQL précise sur la base de données.

Les questions **qualitatives** — par exemple, *"C'est quoi le Net Rating ?"* — qui nécessitent une recherche sémantique dans les documents textuels.

Et les questions **bruitées** — avec des fautes d'orthographe, comme *"kel joueur a le + de passes ?"* — que le système doit quand même être capable de traiter correctement.

*[Passer à la slide 4]*

---

## SLIDE 4 — ARCHITECTURE GLOBALE
### ⏱ 2 minutes

*[Pointer les éléments de haut en bas sur le schéma]*

Voici l'architecture complète du système. Je vais vous guider de haut en bas.

**Les sources de données** sont au sommet : le fichier Excel NBA d'un côté, les quatre PDFs Reddit de l'autre.

Ces sources passent par deux pipelines d'ingestion distincts. Le fichier Excel est traité par `load_excel_to_db.py`, validé par Pydantic, et stocké dans une base **SQLite** — trente équipes, cinq cent soixante-neuf joueurs. Les PDFs sont découpés en chunks et transformés en vecteurs par `indexer.py`, puis stockés dans un **index FAISS** — trois cent deux vecteurs de mille vingt-quatre dimensions.

**Le cœur du système**, c'est le routeur LLM. À chaque question, Mistral analyse la question en moins d'une seconde et décide : est-ce une question pour SQL ou pour RAG ?

Si c'est SQL, le pipeline génère une requête SQL à partir du langage naturel et interroge directement la base de données. Si c'est RAG, le pipeline cherche les chunks les plus proches dans l'index FAISS.

Dans les deux cas, Mistral synthétise un résultat en langage naturel.

Le tout est exposé via deux interfaces : une interface **Streamlit** pour les utilisateurs finaux, et une **API REST FastAPI** pour les intégrations techniques.

À droite sur ce schéma, vous voyez le bloc d'évaluation — j'y reviendrai dans la deuxième partie de la présentation.

*[Passer à la slide 5]*

---

## SLIDE 5 — SOURCES DE DONNÉES & INGESTION
### ⏱ 1 minute 30

**Côté Excel.** Le fichier `regular NBA.xlsx` contient toutes les statistiques de la saison pour les cinq cent soixante-neuf joueurs — des points, des rebonds, des passes, des pourcentages, le Net Rating...

Pour l'ingestion, j'ai créé un pipeline de validation avec **Pydantic** : trois modèles — `TeamRow`, `PlayerRow`, `PlayerStatsRow` — qui vérifient que chaque ligne est cohérente avant d'être insérée en base. Par exemple, un pourcentage de tir ne peut pas dépasser cent. Résultat : zéro erreur de validation sur les cinq cent soixante-neuf joueurs.

Une particularité intéressante : la colonne `3P%` du fichier Excel est lue comme un objet `datetime.time` par pandas à cause d'un bug d'interprétation de format. J'ai résolu ça en accédant à la colonne via `.get("3P%")`.

**Côté PDFs.** Les quatre fichiers Reddit sont découpés en chunks de mille cinq cents caractères avec un chevauchement de cent cinquante. Chaque chunk est ensuite transformé en vecteur par le modèle d'embedding de Mistral — `mistral-embed`. L'index FAISS utilise le produit scalaire, qui est équivalent à la similarité cosinus sur des vecteurs normalisés.

*[Passer à la slide 6]*

---

## SLIDE 6 — PIPELINE RAG
### ⏱ 1 minute 30

*[Pointer les six étapes]*

Le pipeline RAG se déroule en six étapes.

**Étape un** : la question de l'utilisateur est transformée en vecteur via `mistral-embed`.

**Étape deux** : on cherche dans l'index FAISS les cinq chunks les plus proches de ce vecteur par similarité cosinus.

**Étape trois** : on récupère le texte de ces cinq chunks.

**Étape quatre** : on les concatène pour former un contexte.

**Étape cinq** : ce contexte est injecté dans le `RAG_PROMPT` — un prompt qui demande au LLM de répondre *uniquement* à partir du contexte fourni.

**Étape six** : Mistral génère la réponse finale.

**Le point fort** de ce pipeline : il excelle pour les questions qualitatives. Il retrouve les analyses des fans Reddit, les débats sur les styles de jeu, les définitions des métriques avancées.

**Sa limite** — et c'est important — il ne peut pas calculer *"les cinq meilleurs scoreurs de la saison"*. FAISS retrouve des chunks textuels, pas des valeurs agrégées calculées dynamiquement. C'est précisément pour ça qu'on a besoin du pipeline SQL.

*[Passer à la slide 7]*

---

## SLIDE 7 — PIPELINE SQL
### ⏱ 1 minute 30

Le pipeline SQL repose sur une technique appelée **Text-to-SQL avec few-shot prompting**.

Le principe : au lieu d'écrire des requêtes SQL manuellement, on demande au LLM de les générer à partir de la question en langage naturel. Pour guider le LLM, on lui fournit le schéma complet de la base de données — trois tables, trente colonnes documentées — et **huit exemples question-SQL**.

Ces huit exemples couvrent les patterns les plus courants : les top-N joueurs, les filtres avec minimum de matchs joués, les moyennes par équipe, les comparaisons multi-colonnes.

La génération se fait à `temperature=0` pour avoir des requêtes déterministes. Ensuite, la requête est exécutée sur SQLite, le résultat tabulaire est formaté, et Mistral rédige une réponse en langage naturel à partir de ces données.

L'avantage par rapport au RAG : les chiffres sont **exacts**. Aucune approximation, aucune interpolation.

*[Passer à la slide 8]*

---

## SLIDE 8 — ROUTEUR LLM
### ⏱ 1 minute 30

*[Pointer le bloc central ROUTEUR LLM]*

Le routeur, c'est le cerveau de l'agent hybride.

À chaque question, avant de décider quoi faire, on envoie la question à Mistral avec un prompt très court — le `ROUTING_PROMPT` — et on lui demande de répondre en un seul mot : **SQL** ou **RAG**. On limite à cinq tokens maximum, et on met la température à zéro pour avoir une décision déterministe.

*[Pointer colonne gauche]* SQL pour tout ce qui est chiffré : classements, top-N, filtres, moyennes par équipe.

*[Pointer colonne droite]* RAG pour tout ce qui est qualitatif : définitions, analyses de style, débats, contexte historique. C'est aussi le mode de **fallback** si le routeur rencontre une erreur.

Et voici quelque chose d'important : **le routeur est robuste aux questions bruitées**. *"Kel joueur a le + de passes ?"* — malgré les fautes d'orthographe, Mistral comprend qu'il s'agit d'une question statistique et répond SQL.

*[Passer à la slide 9]*

---

## SLIDE 9 — INTERFACES
### ⏱ 1 minute

Le système est accessible via deux interfaces.

**Streamlit** — fichier `MistralChat.py`, port 8501 — propose un chat visuel interactif. L'utilisateur voit clairement quelle source a été utilisée : un badge *"Source : Base de données SQL"* ou *"Source : Base de connaissances RAG"*. Un expander permet d'inspecter les données brutes — la requête SQL exécutée ou les documents sources retrouvés. L'historique de conversation est maintenu pendant toute la session.

**FastAPI** — fichier `api.py`, port 8000 — expose cinq endpoints REST. `GET /health` vérifie que l'index FAISS et la base SQL sont bien chargés. `POST /query` est l'endpoint principal avec routage automatique. Les endpoints `/query/rag` et `/query/sql` permettent de forcer un mode pour les tests. Une documentation Swagger interactive est disponible sur `/docs`.

*[Passer à la slide 10]*

---

## SLIDE 10 — THÉORIE RAGAS
### ⏱ 1 minute 30

Maintenant que j'ai présenté le système, parlons de comment je l'évalue.

**RAGAS** signifie *Retrieval-Augmented Generation Assessment System*. Le principe est d'utiliser un LLM comme juge pour évaluer objectivement les réponses du système. C'est ce qu'on appelle **LLM-as-a-Judge**.

J'ai retenu **trois métriques**.

*[Pointer faithfulness]* La **faithfulness** — ou fidélité — mesure si chaque affirmation de la réponse est ancrée dans le contexte fourni. Un score de 1.0 signifie aucune hallucination. C'est la métrique anti-invention de données.

*[Pointer context_recall]* Le **context_recall** mesure si les documents récupérés couvrent toutes les informations nécessaires pour répondre à la question. Un score de 0.0 signifie que le retrieval n'a rien trouvé d'utile.

*[Pointer context_precision]* La **context_precision** mesure si les K documents retournés sont tous pertinents. Un score proche de 1.0 signifie qu'il y a très peu de bruit dans les résultats.

RAGAS prend en entrée quatre éléments : la question, les contextes récupérés, la réponse générée, et un ground truth — c'est-à-dire la réponse de référence.

*[Passer à la slide 11]*

---

## SLIDE 11 — ARCHITECTURE D'ÉVALUATION
### ⏱ 1 minute

L'évaluation est structurée en trois couches.

**Couche 1 — Pydantic** : elle valide les données à l'entrée et à la sortie. Le modèle `QuestionInput` vérifie que chaque question a bien une catégorie dans l'ensemble `{SIMPLE, COMPLEXE, BRUITÉ}`. Le modèle `RAGResult` nettoie les contextes vides avant qu'ils n'entrent dans RAGAS. Aucune donnée invalide ne peut passer.

**Couche 2 — Pydantic AI** : au lieu d'appeler Mistral directement, j'utilise un `Agent` Pydantic AI avec un type de sortie structuré — `NBAAnswer` — qui a un champ `answer` et un champ `reasoning`. Cela garantit que la réponse est toujours bien formée, jamais null, jamais mal formatée.

**Couche 3 — Logfire** : chaque appel LLM et chaque recherche FAISS est tracé avec sa durée, ses paramètres d'entrée et sa sortie. Le dashboard Logfire donne une visibilité temps réel sur toute la chaîne d'évaluation.

*[Passer à la slide 12]*

---

## SLIDE 12 — RÉSULTATS BASELINE
### ⏱ 1 minute

*[Pointer le tableau]*

Voici les résultats de l'évaluation baseline — le système RAG seul, sans pipeline SQL.

J'ai évalué sur **vingt-cinq questions** réparties en trois catégories : dix questions simples, dix questions complexes, cinq questions bruitées.

Les résultats sont contrastés. La **faithfulness** est à **0.577** — acceptable, le LLM hallucine peu. Mais le **context_recall** est à **0.120** en moyenne — et regardez la colonne COMPLEXE : **zéro**.

Ce zéro n'est pas surprenant, et c'est important à comprendre. FAISS retrouve des chunks textuels — des lignes du dictionnaire Excel, des discussions Reddit. Mais une question comme *"Quels sont les cinq meilleurs scoreurs de la saison ?"* n'a pas de réponse dans les chunks. Il faudrait agréger les données — c'est exactement le rôle du pipeline SQL.

Cette baseline confirme que le RAG seul est insuffisant pour les questions statistiques. C'est la justification directe de l'étape suivante.

*[Passer à la slide 13]*

---

## SLIDE 13 — RÉSULTATS HYBRIDE
### ⏱ 1 minute

*[Pointer le tableau comparatif]*

Voici maintenant les résultats après l'intégration du pipeline SQL — le mode hybride.

Les chiffres sont sans ambiguïté.

La **faithfulness** passe de **0.577** à **0.704** — une hausse de vingt-deux pourcent. Le LLM se base sur des données SQL exactes, il hallucine donc moins.

Le **context_recall** passe de **0.120** à **0.797** — une hausse de **cinq cent soixante-quatre pourcent**. Ce chiffre reflète le fait que le pipeline SQL fournit exactement les données demandées, là où FAISS ne trouvait rien.

La **context_precision** passe de **0.131** à **0.826** — une hausse de cinq cent vingt-neuf pourcent.

*[Pointer le tableau par catégorie]*

Par catégorie, l'impact est encore plus visible. Sur les questions **SIMPLE**, le context_recall atteint **1.000** — le pipeline SQL répond parfaitement aux questions directes. Sur les questions **COMPLEXE**, il passe de **zéro** à **0.759**. Sur les questions **BRUITÉ**, la progression est plus modeste — plus vingt-cinq pourcent — parce que certaines questions sont hors du périmètre des données disponibles.

*[Passer à la slide 14]*

---

## SLIDE 14 — STRUCTURE DU REPO
### ⏱ 30 secondes

*[Pointer rapidement l'arborescence]*

La structure du dépôt est simple et modulaire. Les fichiers principaux sont à la racine. Le dossier `utils/` contient tous les composants réutilisables. Les données sources sont dans `inputs/`, les données générées dans `vector_db/`, `database/`, et `outputs/`.

Chaque fichier a une responsabilité unique et clairement définie.

---

## ⏸ PAUSE — FIN DE LA PRÉSENTATION
**[~14 min 30 écoulées]**

> *"Voilà pour la présentation. Je suis maintenant disponible pour répondre à vos questions."*

---
---

# PARTIE 2 — DISCUSSION AVEC SARAH (10 min)
# Questions attendues & réponses préparées

---

## [SARAH] QUESTION 1 — Interprétation métier des résultats
### Formulation probable : *"Concrètement, ces scores RAGAS — qu'est-ce que ça signifie pour un utilisateur métier ?"*

**Réponse :**

C'est une excellente question, parce que les métriques RAGAS sont des valeurs entre zéro et un, et ça peut sembler abstrait.

Laissez-moi les traduire en termes concrets.

Une **faithfulness de 0.704** signifie que sur dix réponses générées par le système, environ sept sont entièrement fondées sur les données réelles. Les trois autres peuvent contenir des éléments qui vont au-delà du contexte fourni. En pratique, si un analyste pose une question sur les statistiques d'un joueur, il peut faire confiance à la réponse dans sept cas sur dix — et il doit vérifier dans trois cas sur dix.

Un **context_recall de 0.797** signifie que sur dix questions, le système trouve les bonnes informations pour huit d'entre elles. Avant l'intégration SQL, c'était une sur dix. Ce chiffre mesure directement la capacité du système à ne pas "passer à côté" de la réponse.

Pour le monitoring, je recommanderais de surveiller en priorité la **faithfulness** — c'est l'indicateur anti-hallucination. Si elle descend sous 0.65 après une mise à jour du corpus ou du modèle, il faut investiguer.

---

## [SARAH] QUESTION 2 — Robustesse & sensibilité
### Formulation probable : *"Est-ce que le système serait sensible à un changement de corpus ou de modèle de génération ?"*

**Réponse :**

Oui, il y a des sensibilités, et je les ai identifiées.

**Pour un changement de corpus** — une nouvelle saison NBA par exemple — le système est relativement robuste. Il faut relancer `load_excel_to_db.py` pour mettre à jour la base SQL, ce qui prend environ cinq minutes. Il faut aussi relancer `indexer.py` pour ré-indexer les nouveaux PDFs, ce qui prend une quinzaine de minutes. Le schéma SQL et les exemples few-shot restent valides tant que la structure du fichier Excel ne change pas radicalement.

**Pour un changement de modèle de génération** — passer de `mistral-small` à `mistral-medium` par exemple — c'est un seul paramètre à changer dans `config.py`. Les prompts sont écrits pour être modèle-agnostiques.

**La sensibilité principale**, c'est le modèle d'**embedding**. Si on change `mistral-embed` pour un autre modèle d'embedding, il faut obligatoirement reconstruire l'index FAISS — les vecteurs ne sont pas compatibles entre modèles différents. C'est la dépendance la plus forte du système.

La deuxième limite : les données sont des **totaux de saison**. Une question comme *"comment Shai a performé lors des cinq derniers matchs ?"* est impossible à répondre avec ces données. Il faudrait des données par match pour aller plus loin.

---

## [SARAH] QUESTION 3 — Choix techniques
### Formulation probable : *"Pourquoi FAISS et pas ChromaDB ? Pourquoi ces trois métriques et pas answer_relevancy ?"*

**Réponse sur FAISS :**

J'ai choisi FAISS pour trois raisons. Premièrement, c'est en mémoire — aucune infrastructure additionnelle à déployer. Deuxièmement, pour trois cent deux vecteurs, la recherche est quasi-instantanée — moins d'une milliseconde. Troisièmement, `IndexFlatIP` avec des vecteurs normalisés est équivalent à la similarité cosinus exacte, ce qui est ce qu'on veut pour comparer des questions à des chunks de texte.

ChromaDB aurait été plus adapté si on avait eu besoin de filtres sur les métadonnées — par exemple, *"cherche uniquement dans les PDFs de 2025"*. Ce n'est pas un besoin du projet.

**Réponse sur les métriques :**

J'ai retenu faithfulness, context_recall et context_precision parce qu'elles diagnostiquent les trois problèmes principaux d'un système RAG : l'hallucination, la complétude du retrieval, et le bruit dans le retrieval.

J'aurais pu ajouter `answer_relevancy` — qui mesure si la réponse répond bien à la question posée. Je ne l'ai pas fait pour deux raisons : elle nécessite un modèle juge plus puissant pour être fiable, et avec un LLM qui juge un autre LLM du même fournisseur, le risque de biais circulaire est plus élevé. Les trois métriques retenues sont suffisantes pour diagnostiquer le système et prendre des décisions d'amélioration.

---

## [SARAH] QUESTION 4 — Monitoring dans le temps
### Formulation probable : *"Comment puis-je suivre les performances dans le temps ? Comment intégrer ce suivi dans nos rituels de monitoring ?"*

**Réponse :**

Le système est déjà instrumenté pour le monitoring via **Logfire**. Chaque appel LLM et chaque recherche FAISS est tracé avec sa durée, ses paramètres, et sa sortie. Le dashboard Logfire donne une visibilité temps réel sur les latences et les erreurs.

Pour intégrer ce suivi dans des **rituels d'équipe**, je proposerais trois niveaux.

**Au quotidien** : le dashboard Logfire permet de surveiller la latence moyenne et le taux d'erreur du routeur. Si le routeur commence à se tromper plus souvent — ce qui se voit dans les logs — c'est un signal d'alerte.

**Chaque mois** : relancer `evaluate_ragas.py` et `rapport_comparatif.py` pour comparer les métriques avec la baseline. Si la faithfulness descend, il faut vérifier si le corpus a changé ou si le comportement du modèle a évolué.

**Avant chaque déploiement** : mettre en place une règle de gate — par exemple, faithfulness ≥ 0.65 et context_recall ≥ 0.70 — en dessous de laquelle le déploiement est bloqué. Ça peut être automatisé dans une GitHub Action.

Les résultats JSON sont horodatés dans le dossier `outputs/`, ce qui permet de conserver l'historique des évaluations et de tracer des courbes de performance dans le temps.

---

## [SARAH] QUESTION 5 — Question surprise possible
### *"Si on voulait industrialiser ce système, qu'est-ce qui manque ?"*

**Réponse :**

Plusieurs choses.

**Premièrement**, le système répond à une question avec *une seule source* — SQL ou RAG. Pour les questions mixtes — *"Donne-moi les stats de Wembanyama et explique son style de jeu"* — il faudrait un mode hybride qui interroge les deux sources en parallèle et fusionne les réponses.

**Deuxièmement**, il n'y a pas de cache. Les mêmes requêtes SQL sont réexécutées à chaque appel. En production, un cache Redis sur les requêtes fréquentes réduirait la latence et les coûts API.

**Troisièmement**, les données sont statiques — saison complète uniquement. Pour un usage professionnel, il faudrait une connexion à l'API NBA officielle pour des données en temps réel.

Et **quatrièmement**, pour aller plus loin sur l'évaluation, je rajouterais `answer_relevancy` avec un modèle évaluateur indépendant du modèle de génération — pour éviter le biais du LLM-as-judge qui évalue son propre travail.

---
---

# RÉCAPITULATIF TIMING

| Slide | Contenu | Temps |
|---|---|---|
| 1 | Couverture | 30 s |
| 2 | Plan | 30 s |
| 3 | Contexte & Objectifs | 1 min |
| 4 | Architecture globale | 2 min |
| 5 | Sources & Ingestion | 1 min 30 |
| 6 | Pipeline RAG | 1 min 30 |
| 7 | Pipeline SQL | 1 min 30 |
| 8 | Routeur LLM | 1 min 30 |
| 9 | Interfaces | 1 min |
| 10 | Théorie RAGAS | 1 min 30 |
| 11 | Architecture évaluation | 1 min |
| 12 | Résultats baseline | 1 min |
| 13 | Résultats hybride | 1 min |
| 14 | Repo Git | 30 s |
| **TOTAL** | | **~15 min** |

---

# PHRASES CLÉS À RETENIR

> *"Le routeur LLM décide en moins d'une seconde si la question appelle une requête SQL exacte ou une recherche sémantique dans les documents."*

> *"Context_recall de 0.000 sur les questions COMPLEXE en RAG seul — ce n'est pas un échec, c'est la confirmation que FAISS n'est pas fait pour les agrégations statistiques."*

> *"Après intégration SQL : context_recall +564 %. Le pipeline SQL transforme radicalement les performances."*

> *"Trois couches de robustesse : Pydantic valide les données, Pydantic AI structure les réponses, Logfire trace tout."*

> *"La faithfulness, c'est l'indicateur anti-hallucination. Si elle descend sous 0.65, il faut investiguer."*
