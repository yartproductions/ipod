import Foundation
import UserNotifications

extension Notification.Name {
    /// Posted when the wake-up alarm goes off (or its notification is tapped); the web view starts the music.
    static let ipodWakeUp = Notification.Name("ipodWakeUp")
}

/// Schedules the iPod's Wake-Up Alarm as a local notification. When it fires with the app open, or when
/// you tap it from the Lock Screen, the page's `window.ipodWakeUp()` starts the wake-up playlist.
final class IPodAlarm: NSObject, UNUserNotificationCenterDelegate {
    static let shared = IPodAlarm()
    private static let requestID = "ipod.wakeup"
    /// Set when a wake-up arrives before the page is ready; the web view picks it up once it loads.
    private(set) var pendingWake = false

    func install() { UNUserNotificationCenter.current().delegate = self }

    func schedule(hour: Int, minute: Int, repeats: Bool, label: String) {
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
            when.hour = max(0, min(23, hour)); when.minute = max(0, min(59, minute))
            let trigger = UNCalendarNotificationTrigger(dateMatching: when, repeats: repeats)
            center.add(UNNotificationRequest(identifier: Self.requestID, content: content, trigger: trigger))
        }
    }

    func cancel() {
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: [Self.requestID])
    }

    func takePendingWake() -> Bool { defer { pendingWake = false }; return pendingWake }

    private func wake() {
        DispatchQueue.main.async {
            self.pendingWake = true
            NotificationCenter.default.post(name: .ipodWakeUp, object: nil)
        }
    }

    // App open when the alarm fires: start the music straight away, no banner.
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
}
