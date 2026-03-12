package com.example.store.service;

import com.example.store.repository.UserRepository;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

@Service
public class UserService {

    private final UserRepository userRepository;
    private final WebClient webClient;

    public UserService(UserRepository userRepository, WebClient webClient) {
        this.userRepository = userRepository;
        this.webClient = webClient;
    }

    // PROBLEMA: Thread.sleep() bloqueia thread do pool de forma fixa
    // → aciona THREAD_BLOCKING: degradação linear sob carga
    public void processWithDelay() throws InterruptedException {
        Thread.sleep(500); // bloqueia thread
        doProcess();
    }

    // PROBLEMA: .block() bloqueia em contexto reativo
    // → aciona THREAD_BLOCKING: viola o modelo non-blocking do WebFlux
    public String fetchUserData(String userId) {
        return webClient.get()
                .uri("/api/users/" + userId)
                .retrieve()
                .bodyToMono(String.class)
                .block(); // bloqueia thread reativa
    }

    private void doProcess() {
        // processamento interno
    }
}
