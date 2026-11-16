import Foundation
import SwiftUI
import UserNotifications
#if canImport(AlarmKit)
import AlarmKit
import AppIntents
#endif

extension Notification.Name {
    /// Posted when the wake-up alarm goes off (or is tapped); the web view starts the music.
    static let ipodWakeUp = Notification.Name("ipodWakeUp")
}

/// The iPod's Wake-Up Alarm.
///
/// - iOS 26+: a real AlarmKit alarm. It rings through Silent mode and Focus with the full-screen
///   alarm UI on the Lock Screen; its "Play Music" button opens the iPod and starts the wake-up playlist.
///   If the iPod is still running in "night mode" (you fell asleep with the Sleep Timer), the app
///   silences the alarm the moment it starts and fades the music in itself, with the phone still locked.
/// - Older iOS: a local notification; tapping it starts the music.
final class IPodAlarm: NSObject, UNUserNotificationCenterDelegate {
    static let shared = IPodAlarm()
    private static let requestID = "ipod.wakeup"
    private static let alarmIDKey = "ipod.alarmkit.id"
    /// Set when a wake-up arrives before the page is ready; the web view picks it up once it loads.
    private(set) var pendingWake = false
    /// True while the page keeps itself alive overnight after the Sleep Timer (it reports this).
    var nightMode = false

    func install() {
        UNUserNotificationCenter.current().delegate = self
        #if canImport(AlarmKit)
        if #available(iOS 26.0, *) { watchAlarms() }
        #endif
    }

    func schedule(hour: Int, minute: Int, repeats: Bool, label: String) {
        let h = max(0, min(23, hour)), m = max(0, min(59, minute))
        #if canImport(AlarmKit)
        if #available(iOS 26.0, *) {
            Task { await scheduleAlarmKit(hour: h, minute: m, repeats: repeats) }
            return
        }
        #endif
        scheduleNotification(hour: h, minute: m, repeats: repeats, label: label)
    }

    func cancel() {
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: [Self.requestID])
        #if canImport(AlarmKit)
        if #available(iOS 26.0, *) { cancelAlarmKit() }
        #endif
    }

    func takePendingWake() -> Bool { defer { pendingWake = false }; return pendingWake }

    fileprivate func wake() {
        DispatchQueue.main.async {
            self.pendingWake = true
            NotificationCenter.default.post(name: .ipodWakeUp, object: nil)
        }
    }

    // MARK: Notification fallback (before iOS 26)

    private func scheduleNotification(hour: Int, minute: Int, repeats: Bool, label: String) {
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
            guard granted else { return }
            center.removePendingNotificationRequests(withIdentifiers: [Self.requestID])
            let content = UNMutableNotificationContent()
            content.title = "Good morning"
            content.body = "Tap to wake up to \(label)."
            content.sound = .default
            if #available(iOS 15.0, *) { content.interruptionLevel = .active }
            var when = DateComponents()
            when.hour = hour; when.minute = minute
            let trigger = UNCalendarNotificationTrigger(dateMatching: when, repeats: repeats)
            center.add(UNNotificationRequest(identifier: Self.requestID, content: content, trigger: trigger))
        }
    }

    // App open when the notification fires: start the music straight away, no banner.
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        guard notification.request.identifier == Self.requestID else { return completionHandler([.banner, .sound]) }
        wake()
        completionHandler([])
    }

    // Tapped from the Lock Screen or Notification Center.
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        if response.notification.request.identifier == Self.requestID { wake() }
        completionHandler()
    }

    // MARK: AlarmKit (iOS 26+)

    #if canImport(AlarmKit)
    @available(iOS 26.0, *)
    private var savedAlarmID: UUID? {
        get { UserDefaults.standard.string(forKey: Self.alarmIDKey).flatMap(UUID.init(uuidString:)) }
        set { UserDefaults.standard.set(newValue?.uuidString, forKey: Self.alarmIDKey) }
    }

    @available(iOS 26.0, *)
    private func cancelAlarmKit() {
        if let id = savedAlarmID { try? AlarmManager.shared.cancel(id: id) }
        savedAlarmID = nil
    }

    @available(iOS 26.0, *)
    private func scheduleAlarmKit(hour: Int, minute: Int, repeats: Bool) async {
        let manager = AlarmManager.shared
        do {
            if manager.authorizationState != .authorized {
                guard try await manager.requestAuthorization() == .authorized else {
                    // Alarms not allowed: fall back to the notification so you still get woken.
                    scheduleNotification(hour: hour, minute: minute, repeats: repeats, label: "your music")
                    return
                }
            }
            cancelAlarmKit()
            UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: [Self.requestID])

            let alert = AlarmPresentation.Alert(
                title: "Good morning",
                secondaryButton: AlarmButton(text: "Play Music", textColor: .white, systemImageName: "music.note"),
                secondaryButtonBehavior: .custom)
            let attributes = AlarmAttributes<IPodAlarmMetadata>(
                presentation: AlarmPresentation(alert: alert),
                metadata: IPodAlarmMetadata(),
                tintColor: Color(red: 0.24, green: 0.80, blue: 0.45))
            let time = Alarm.Schedule.Relative.Time(hour: hour, minute: minute)
            let schedule = Alarm.Schedule.relative(.init(
                time: time,
                repeats: repeats ? .weekly([.sunday, .monday, .tuesday, .wednesday, .thursday, .friday, .saturday]) : .never))
            let configuration = AlarmManager.AlarmConfiguration.alarm(
                schedule: schedule,
                attributes: attributes,
                stopIntent: nil,
                secondaryIntent: PlayWakeMusicIntent(),
                sound: .default)
            let id = UUID()
            _ = try await manager.schedule(id: id, configuration: configuration)
            savedAlarmID = id
        } catch {
            print("iPod alarm: AlarmKit scheduling failed, using a notification instead:", error)
            scheduleNotification(hour: hour, minute: minute, repeats: repeats, label: "your music")
        }
    }

    /// While the app is alive (night mode after the Sleep Timer, or simply open), take over the
    /// moment the alarm starts ringing: stop the system alarm sound and fade the music in instead.
    @available(iOS 26.0, *)
    private func watchAlarms() {
        Task {
            for await alarms in AlarmManager.shared.alarmUpdates {
                guard let id = savedAlarmID, let mine = alarms.first(where: { $0.id == id }),
                      mine.state == .alerting else { continue }
                let appActive = await MainActor.run { UIApplication.shared.applicationState == .active }
                if nightMode || appActive {
                    try? AlarmManager.shared.stop(id: id)
                    wake()
                }
            }
        }
    }
    #endif
}

#if canImport(AlarmKit)
@available(iOS 26.0, *)
struct IPodAlarmMetadata: AlarmMetadata {}

/// "Play Music" on the alarm: opens the iPod and starts the wake-up playlist.
@available(iOS 26.0, *)
struct PlayWakeMusicIntent: LiveActivityIntent {
    static let title: LocalizedStringResource = "Play Wake-Up Music"
    static let description = IntentDescription("Opens the iPod and plays your wake-up music.")
    static let openAppWhenRun: Bool = true
    init() {}
    func perform() async throws -> some IntentResult {
        IPodAlarm.shared.wake()
        return .result()
    }
}
#endif
