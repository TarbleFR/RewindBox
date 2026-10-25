import SwiftUI
import GameController

struct MeloNXMappingView: View {
    @ObservedObject var router: MeloNXInputRouter
    @Environment(\.dismiss) private var dismiss
    @State private var selected = 0
    @State private var mapping = ControllerMapping.standard()
    @State private var error: String?
    var body: some View {
        NavigationView {
            Form {
                if router.controllers.isEmpty { Text(MeloNXText("Connect a controller")) }
                else {
                    Picker(MeloNXText("Controller"),selection:$selected) {
                        ForEach(Array(router.controllers.enumerated()),id:\.offset) { index, controller in
                            Text(controller.vendorName ?? "Controller").tag(index)
                        }
                    }
                    Section(header:Text(router.gameName)) {
                        ForEach(VirtualControllerButton.bindable) { button in
                            Picker(MeloNXText(button.switchDisplayName),selection:Binding(get:{mapping[button]},set:{mapping[button] = $0})) {
                                ForEach(PhysicalInput.assignable) { input in Text(MeloNXText(input.displayName)).tag(input) }
                            }
                        }
                    }
                    Picker(MeloNXText("Left Stick"),selection:$mapping.leftStick.source) {
                        ForEach(PhysicalStick.allCases) { Text(MeloNXText($0.displayName)).tag($0) }
                    }
                    Picker(MeloNXText("Right Stick"),selection:$mapping.rightStick.source) {
                        ForEach(PhysicalStick.allCases) { Text(MeloNXText($0.displayName)).tag($0) }
                    }
                    Button(MeloNXText("Reset")) { mapping = .standard() }
                    Button(MeloNXText("Save")) {
                        guard router.controllers.indices.contains(selected) else { return }
                        do { try router.save(mapping,for:router.controllers[selected]); dismiss() }
                        catch { self.error = error.localizedDescription }
                    }
                }
                if let error { Text(error).foregroundStyle(.red) }
            }
            .navigationTitle(MeloNXText("Controller mapping"))
            .toolbar { ToolbarItem(placement:.cancellationAction) { Button(MeloNXText("Done")) { dismiss() } } }
            .onAppear { reload() }.onChange(of:selected) { _ in reload() }
            .onChange(of:router.controllerCount) { _ in selected = 0; reload() }
        }
    }
    private func reload() {
        guard router.controllers.indices.contains(selected) else { return }
        mapping = router.mapping(for:router.controllers[selected])
    }
}
