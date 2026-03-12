package com.example.store.service;

import com.example.store.model.Item;
import com.example.store.model.Order;
import com.example.store.repository.ItemRepository;
import com.example.store.repository.OrderRepository;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.concurrent.CompletableFuture;

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final ItemRepository itemRepository;

    public OrderService(OrderRepository orderRepository, ItemRepository itemRepository) {
        this.orderRepository = orderRepository;
        this.itemRepository = itemRepository;
    }

    // PROBLEMA: N+1 — para cada order, faz uma query extra ao banco
    // → aciona N+1_QUERY: deve usar JOIN FETCH ou @EntityGraph
    public List<Order> processOrders() {
        List<Order> orders = orderRepository.findAll();
        for (Order order : orders) {
            List<Item> items = itemRepository.findByOrder(order); // N+1 aqui
        }
        return orders;
    }

    // PROBLEMA: future.get() bloqueia a thread do servidor
    // → aciona THREAD_BLOCKING: usar thenApply() em vez de .get()
    public String fetchExternalData() throws Exception {
        CompletableFuture<String> future = CompletableFuture.supplyAsync(() -> {
            return callExternalService();
        });
        return future.get(); // bloqueia thread
    }

    private String callExternalService() {
        return "external-data";
    }
}
