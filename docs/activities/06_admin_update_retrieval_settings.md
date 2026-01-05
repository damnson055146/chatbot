# Admin Update Retrieval Settings

```plantuml
@startuml
skinparam shadowing false
skinparam backgroundColor White
skinparam activityBorderColor Black
skinparam activityBackgroundColor White
skinparam activityDiamondBorderColor Black
skinparam activityDiamondBackgroundColor White
skinparam activityStartColor Black
skinparam activityEndColor Black
skinparam swimlaneBorderColor Black
skinparam swimlaneBorderThickness 1
skinparam swimlaneTitleBackgroundColor White
skinparam swimlaneTitleBorderColor Black
skinparam swimlaneTitleBorderThickness 1
skinparam padding 20
title Admin Update Retrieval Settings
|User|
start
:Open admin config;
|System|
:Load retrieval settings;
|User|
:Edit retrieval settings;
:Click save;
|System|
:Update retrieval settings;
:Refresh config view;
stop
@enduml
```
