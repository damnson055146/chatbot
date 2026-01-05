@startuml
left to right direction
skinparam shadowing false
skinparam linetype spline
skinparam ranksep 45
skinparam nodesep 35
skinparam actorStyle awesome
skinparam usecaseBackgroundColor White
skinparam usecaseBorderColor Black
skinparam rectangleBorderColor Black
skinparam packageStyle rectangle
skinparam padding 15

actor Admin
actor User

rectangle "Study Abroad RAG Assistant System" {
  (Manage Jobs) as UC_AdminJobs
  (Manage Prompts) as UC_AdminPrompts
  (Manage Sources) as UC_AdminSources
  (Update Assistant Opening) as UC_AdminOpening
  (Update Assistant Profile) as UC_AdminProfile
  (Update Retrieval Settings) as UC_AdminRetrieval
  (Upload Source Files) as UC_AdminUpload
  (View Metrics) as UC_ViewMetrics
  (View Status) as UC_ViewStatus

  (Ask Question) as UC_Ask
  (Legacy Answer Mode) as UC_LegacyAnswer
  (Legacy Query Mode) as UC_LegacyQuery
  (Stop Response Streaming) as UC_StopStreaming
  (Submit Feedback) as UC_SubmitFeedback
  (View Citations) as UC_ViewCitations
  (View Citation Detail) as UC_ViewCitationDetail
  (View Assistant Profile) as UC_ViewAssistant
  (Open Conversation) as UC_OpenConversation
  (Search Conversations) as UC_SearchConversations
  (Rename Conversation) as UC_RenameConversation
  (Delete Conversation) as UC_DeleteConversation
  (Export Conversation History) as UC_ExportHistory
  (Login) as UC_Login
  (Register) as UC_Register
  (Logout) as UC_Logout
  (Manage User Profile) as UC_ManageUserProfile
  (Reset Password) as UC_ResetPassword

  UC_AdminJobs -[hidden]down- UC_AdminPrompts
  UC_AdminPrompts -[hidden]down- UC_AdminSources
  UC_AdminSources -[hidden]down- UC_AdminOpening
  UC_AdminOpening -[hidden]down- UC_AdminProfile
  UC_AdminProfile -[hidden]down- UC_AdminRetrieval
  UC_AdminRetrieval -[hidden]down- UC_AdminUpload
  UC_AdminUpload -[hidden]down- UC_ViewMetrics
  UC_ViewMetrics -[hidden]down- UC_ViewStatus

  UC_Ask -[hidden]down- UC_LegacyAnswer
  UC_LegacyAnswer -[hidden]down- UC_LegacyQuery
  UC_LegacyQuery -[hidden]down- UC_StopStreaming
  UC_StopStreaming -[hidden]down- UC_SubmitFeedback
  UC_SubmitFeedback -[hidden]down- UC_ViewCitations
  UC_ViewCitations -[hidden]down- UC_ViewCitationDetail
  UC_ViewCitationDetail -[hidden]down- UC_ViewAssistant
  UC_ViewAssistant -[hidden]down- UC_OpenConversation
  UC_OpenConversation -[hidden]down- UC_SearchConversations
  UC_SearchConversations -[hidden]down- UC_RenameConversation
  UC_RenameConversation -[hidden]down- UC_DeleteConversation
  UC_DeleteConversation -[hidden]down- UC_ExportHistory
  UC_ExportHistory -[hidden]down- UC_Login
  UC_Login -[hidden]down- UC_Register
  UC_Register -[hidden]down- UC_Logout
  UC_Logout -[hidden]down- UC_ManageUserProfile
  UC_ManageUserProfile -[hidden]down- UC_ResetPassword

  UC_AdminJobs -[hidden]right- UC_Ask
}

Admin --> UC_AdminJobs
Admin --> UC_AdminPrompts
Admin --> UC_AdminSources
Admin --> UC_AdminOpening
Admin --> UC_AdminProfile
Admin --> UC_AdminRetrieval
Admin --> UC_AdminUpload
Admin --> UC_ViewMetrics
Admin --> UC_ViewStatus

User -left-> UC_Ask
User -left-> UC_LegacyAnswer
User -left-> UC_LegacyQuery
User -left-> UC_StopStreaming
User -left-> UC_SubmitFeedback
User -left-> UC_ViewCitations
User -left-> UC_ViewCitationDetail
User -left-> UC_ViewAssistant
User -left-> UC_OpenConversation
User -left-> UC_SearchConversations
User -left-> UC_RenameConversation
User -left-> UC_DeleteConversation
User -left-> UC_ExportHistory
User -left-> UC_Login
User -left-> UC_Register
User -left-> UC_Logout
User -left-> UC_ManageUserProfile
User -left-> UC_ResetPassword
UC_ResetPassword -[hidden]right- User
@enduml