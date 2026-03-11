package com.example.demo.service;

import com.example.demo.model.Order;
import org.springframework.stereotype.Service;

import javax.persistence.OneToMany;
import java.util.List;
import java.util.concurrent.CompletableFuture;

/**
 * PROBLEMAS DE PERFORMANCE INTENCIONAIS (sample para SentinelCode Fase 3):
 *
 * 1. @OneToMany sem FetchType.EAGER e sem @JsonManagedReference
 *    → LazyInitializationException durante serialização JSON
 *
 * 2. future.get() — bloqueia thread do servidor aguardando resultado
 *    → reduz throughput máximo da API
 *
 * 3. Thread.sleep() — bloqueia thread do pool
 *    → degradação linear sob carga
 */
@Service
public class UserService {

    // PROBLEMA: @OneToMany lazy sem @JsonManagedReference
    // A serialização Jackson pode causar LazyInitializationException
    @OneToMany
    private List<Order> orders;

    public String fetchExternalData() throws Exception {
        CompletableFuture<String> future = CompletableFuture.supplyAsync(() -> {
            return "external-data";
        });

        // PROBLEMA: .get() bloqueia a thread do servidor
        return future.get();
    }

    public void processWithDelay() throws InterruptedException {
        // PROBLEMA: Thread.sleep() bloqueia thread do pool
        Thread.sleep(500);
        doProcess();
    }

    public String reactiveCall() {
        // PROBLEMA: .block() bloqueia em contexto reativo
        return webClient.get()
            .uri("/api/data")
            .retrieve()
            .bodyToMono(String.class)
            .block();
    }

    private void doProcess() {
        // processamento
    }
}
